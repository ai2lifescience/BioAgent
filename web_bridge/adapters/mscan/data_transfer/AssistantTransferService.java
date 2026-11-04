package com.mscan.web.controller.common;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.mscan.common.core.domain.BaseEntity;
import com.mscan.database.domain.entity.*;
import com.mscan.database.mapper.*;
import com.mscan.database.service.ISampleFileService;
import com.mscan.database.service.storage.ObjectStorageReader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;
import org.springframework.transaction.PlatformTransactionManager;
import java.util.*;
import java.util.concurrent.*;
import jakarta.annotation.PreDestroy;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;

/** MSCAN adapter for the generic durable transfer protocol. No browser/session impersonation. */
@Service
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class AssistantTransferService {
    @org.springframework.beans.factory.annotation.Autowired private ResultImporterRegistry importerRegistry;
    @org.springframework.beans.factory.annotation.Autowired private TransferLocks locks;
    private final int concurrency;
    private final Semaphore capacity;
    private final ExecutorService workers;
    private final Set<String> active=ConcurrentHashMap.newKeySet();
    private volatile boolean closed;
    private final AssistantController bridge;
    private final AssistantDeliveryService delivery;
    private final IProjectMapper projects;
    private final IMetadataMapper metadata;
    private final IFastSampleMapper fasta;
    private final ISampleInfoMapper info;
    private final ISampleFileService files;
    private final ObjectStorageReader storage;
    private final TransactionTemplate transaction;
    @Value("${minio.bucketName}") private String bucket;
    public AssistantTransferService(AssistantController bridge,AssistantDeliveryService delivery,IProjectMapper projects,IMetadataMapper metadata,IFastSampleMapper fasta,ISampleInfoMapper info,ISampleFileService files,ObjectStorageReader storage,PlatformTransactionManager tx,
            @Value("${bioagent.transfer-workers:3}") int concurrency) {
        if(concurrency<1)throw new IllegalArgumentException("bioagent.transfer-workers must be positive.");
        this.concurrency=concurrency;this.capacity=new Semaphore(concurrency);
        this.workers=new ThreadPoolExecutor(concurrency,concurrency,0L,TimeUnit.MILLISECONDS,
            new ArrayBlockingQueue<>(concurrency),r->{var thread=new Thread(r,"agent-transfer");thread.setDaemon(true);return thread;});
        this.bridge=bridge;this.delivery=delivery;this.projects=projects;this.metadata=metadata;this.fasta=fasta;this.info=info;this.files=files;this.storage=storage;this.transaction=new TransactionTemplate(tx);
    }
    @Scheduled(fixedDelayString="${bioagent.transfer-poll-ms:2000}")
    public synchronized void poll() {
        // Reserve capacity before leasing: commands must not expire in a local queue.
        for(int i=0;i<concurrency&&!closed&&capacity.tryAcquire();i++) {
            boolean submitted=false;String id=null;
            try {
                var command=nextCommand();
                if(command==null)break;
                id=(String)command.get("id");
                // If a heartbeat was lost, let the replacement lease expire rather
                // than executing the same command twice in this process.
                if(!active.add(id)){id=null;break;}
                final String commandId=id;
                workers.execute(()->{
                    try {runCommand(command);}
                    finally {active.remove(commandId);capacity.release();}
                });
                submitted=true;
            } catch(Exception error) {
                org.slf4j.LoggerFactory.getLogger(getClass()).debug("Agent transfer unavailable: {}",error.getClass().getSimpleName());
                break;
            } finally {
                if(!submitted){if(id!=null)active.remove(id);capacity.release();}
            }
        }
    }
    Map<String,Object> nextCommand() throws Exception {
        var pending=bridge.callAs("connector","commands",Map.of("exclude_ids",List.copyOf(active),"capabilities",Map.of(
            "operations",List.of("search","pull","push"),"destination_fields",Map.of(
                "project","Exact owned project ID or name", "sample","Exact sample ID or name in the project",
                "data_type","meta, shortReads, genomic or synthetic", "source_slots","Optional map of R1/R2 or genome to selected workspace paths"),
            "create_missing",true,"existing_sources","preserved","native_result_importers",importerRegistry.capabilities())));
        var commands=(List<Map<String,Object>>)pending.getOrDefault("commands",List.of());
        return commands.isEmpty()?null:commands.get(0);
    }
    private void runCommand(Map<String,Object> command) {
        var ack=new HashMap<String,Object>();ack.put("id",command.get("id"));ack.put("lease",command.get("lease"));
        var heartbeat=Executors.newSingleThreadScheduledExecutor(r->{var thread=new Thread(r,"agent-transfer-heartbeat");thread.setDaemon(true);return thread;});
        try {
            heartbeat.scheduleAtFixedRate(()->{try{bridge.callAs("connector","command-heartbeat",Map.of("id",command.get("id"),"lease",command.get("lease")));}catch(Exception ignored){}},30,30,TimeUnit.SECONDS);
            try {ack.put("result",execute(command));ack.put("ok",true);}
            catch(Exception error){
                var failure=new HashMap<String,Object>();failure.put("error",error.getClass().getSimpleName()+": "+error.getMessage());
                if("push".equals(command.get("operation")))try {
                    delivery.results((String)command.get("subject"),"").stream().filter(r->command.get("id").equals(r.get("id"))).findFirst().ifPresent(receipt->{
                        failure.put("file_delivery","delivered");failure.put("native_imports",receipt.getOrDefault("native_imports",List.of()));failure.put("target",receipt.get("target"));
                    });
                } catch(Exception ignored) { /* Preserve the original failure. */ }
                ack.put("ok",false);ack.put("result",failure);
            }
            bridge.callAs("connector","command-ack",ack);
        } catch(Exception error) {
            // Leave an unacknowledged lease for durable retry after expiry.
            org.slf4j.LoggerFactory.getLogger(getClass()).debug("Agent transfer acknowledgement unavailable: {}",error.getClass().getSimpleName());
        } finally {heartbeat.shutdownNow();}
    }
    @PreDestroy
    public void close() {closed=true;workers.shutdownNow();}
    Map<String,Object> execute(Map<String,Object> command) throws Exception {
        String owner=(String)command.get("subject"),id=(String)command.get("id");
        var payload=(Map<String,Object>)command.get("payload");
        switch((String)command.get("operation")) {
            case "search":return search(owner,payload);
            case "pull":return Map.of("file",bridge.pullCommand(owner,(String)command.get("session_id"),id,(String)payload.get("resource_id")));
            case "push": {
                var destination=new HashMap<String,Object>((Map<String,Object>)payload.get("destination"));destination.put("create_missing",payload.get("create_missing"));
                var slots=sourceSlots(destination,(List<Map<String,Object>>)payload.get("files"));
                Map<String,Object> target;
                // Serialize only destination creation for this owner, including aliases.
                try(var ownerLock=locks.owner(owner)) {target=transaction.execute(status->destination(owner,destination));}
                try(var sampleLock=locks.sample(owner,(String)target.get("sample_id"))) {
                    var item=new HashMap<String,Object>(command);item.put("target",target);item.put("files",payload.get("files"));
                    delivery.receive(item,"command-artifact");
                    var receipt=delivery.results(owner,(String)target.get("sample_id")).stream().filter(r->id.equals(r.get("id"))).findFirst().orElseThrow();
                    var registration=registerSources(owner,id,target,(List<Map<String,Object>>)receipt.get("files"),slots);
                    return Map.of("target",target,"receipt_id",id,"files",receipt.get("files"),"source_registration",registration,
                        "native_qc_applied",receipt.getOrDefault("native_qc_applied",false),"qc",receipt.getOrDefault("qc",Map.of()),
                        "file_delivery","delivered","native_imports",receipt.getOrDefault("native_imports",List.of()));
                }
            }
            default:throw new IllegalArgumentException("Unsupported command.");
        }
    }
    private Map<String,Object> search(String owner,Map<String,Object> payload) throws Exception {
        String query=String.valueOf(payload.getOrDefault("query","")).toLowerCase(Locale.ROOT);List<Map<String,Object>> all=new ArrayList<>();
        for(var p:projects.selectList(new QueryWrapper<Project>().eq("create_by",owner)))all.add(Map.of("kind","project","id",p.getId(),"name",p.getProjectName(),"project_type",p.getProjectType()));
        int offset=0;
        while(true){var page=bridge.catalog(owner,"",offset,200);var rows=(List<Map<String,Object>>)page.get("resources");all.addAll(rows);offset+=rows.size();if(offset>=((Number)page.get("total")).intValue()||rows.isEmpty())break;}
        var matches=all.stream().filter(r->r.values().stream().anyMatch(v->String.valueOf(v).toLowerCase(Locale.ROOT).contains(query))).toList();
        int start=Math.min(matches.size(),Math.max(0,((Number)payload.getOrDefault("offset",0)).intValue()));
        return Map.of("resources",matches.subList(start,Math.min(matches.size(),start+100)),"total",matches.size(),"offset",start);
    }
    private String text(Map<String,Object> p,String key) {
        String value=String.valueOf(p.getOrDefault(key,"")).trim();if(value.isEmpty()||value.length()>120)throw new IllegalArgumentException("Provide "+key+" (1–120 characters).");return value;
    }
    private static String stable(String value){return UUID.nameUUIDFromBytes(value.getBytes(StandardCharsets.UTF_8)).toString().replace("-","");}
    private static void owned(BaseEntity row,String owner){row.setCreateBy(owner);row.setUpdateBy(owner);row.setCreateTime(new Date());row.setUpdateTime(new Date());row.setDelFlag("0");}
    private Map<String,Object> destination(String owner,Map<String,Object> p) {
        String project=text(p,"project"),sample=text(p,"sample"),type=text(p,"data_type");
        if(!List.of("meta","shortReads","genomic","synthetic").contains(type))throw new IllegalArgumentException("Unknown sample type.");
        boolean create=Boolean.TRUE.equals(p.get("create_missing"));int projectType=type.equals("genomic")?2:type.equals("synthetic")?3:1;
        var candidates=projects.selectList(new QueryWrapper<Project>().eq("create_by",owner).eq("project_type",projectType).and(q->q.eq("id",project).or().eq("project_name",project)));
        if(candidates.size()>1)throw new IllegalArgumentException("Ambiguous project; use its ID.");
        Project target=candidates.isEmpty()?null:candidates.get(0);
        if(target==null){if(!create)throw new IllegalArgumentException("Project not found.");target=new Project();owned(target,owner);target.setId(stable(owner+":"+projectType+":"+project));target.setProjectName(project);target.setProjectType(projectType);target.setParentId("0");target.setDescription("Created through the agent website connector.");projects.insert(target);}
        String sid;
        if(projectType==1) {
            var rows=metadata.selectList(new QueryWrapper<Metadata>().eq("create_by",owner).eq("project_id",target.getId()).eq("data_type",type).and(q->q.eq("id",sample).or().eq("sample_name",sample)));
            if(rows.size()>1)throw new IllegalArgumentException("Ambiguous sample; use its ID.");
            if(rows.isEmpty()) {if(!create)throw new IllegalArgumentException("Sample not found.");var row=new Metadata();owned(row,owner);row.setId(stable(owner+":"+target.getId()+":"+type+":"+sample));row.setSampleName(sample);row.setProjectId(target.getId());row.setDataType(type);metadata.insert(row);sid=row.getId();var summary=new SampleInfo();summary.setSampleId(sid);owned(summary,owner);info.insert(summary);}
            else sid=rows.get(0).getId();
        } else {
            var rows=fasta.selectList(new QueryWrapper<FastaSample>().eq("create_by",owner).eq("project_id",target.getId()).and(q->q.eq("id",sample).or().eq("sample_name",sample)));
            if(rows.size()>1)throw new IllegalArgumentException("Ambiguous sample; use its ID.");
            if(rows.isEmpty()){if(!create)throw new IllegalArgumentException("Sample not found.");var row=new FastaSample();owned(row,owner);row.setId(stable(owner+":"+target.getId()+":"+type+":"+sample));row.setSampleName(sample);row.setProjectId(target.getId());row.setDataType(type.equals("genomic")?"genome":type);fasta.insert(row);sid=row.getId();}
            else sid=rows.get(0).getId();
        }
        return Map.of("project_id",target.getId(),"project_name",target.getProjectName(),"sample_id",sid,"sample_name",sample,"data_type",type);
    }
    private Map<String,String> sourceSlots(Map<String,Object> destination,List<Map<String,Object>> files) {
        boolean reads=List.of("meta","shortReads").contains(destination.get("data_type"));
        Map<String,String> slots=new HashMap<>();
        if(destination.get("source_slots") instanceof Map<?,?> specified)for(var e:specified.entrySet())slots.put(String.valueOf(e.getKey()),String.valueOf(e.getValue()));
        var paths=files.stream().map(f->String.valueOf(f.getOrDefault("workspace_path",f.get("path")))).toList();
        for(var e:slots.entrySet())if(!(reads?List.of("R1","R2"):List.of("genome")).contains(e.getKey())||!paths.contains(e.getValue()))throw new IllegalArgumentException("Source slot must reference a selected file with a supported role.");
        if(slots.containsKey("R2")&&!slots.containsKey("R1"))throw new IllegalArgumentException("R2 requires R1.");
        if(new HashSet<>(slots.values()).size()!=slots.size())throw new IllegalArgumentException("Source roles must use distinct files.");
        if(slots.isEmpty()) {
            var candidates=files.stream().filter(f->!"pipeline_output".equals(f.get("kind")))
                .map(f->String.valueOf(f.getOrDefault("workspace_path",f.get("path"))))
                .filter(p->p.toLowerCase(Locale.ROOT).matches(reads?".*\\.(fastq|fq)(\\.gz)?":".*\\.(fasta|fa|fna)(\\.gz)?")).toList();
            if(candidates.size()==1)slots.put(reads?"R1":"genome",candidates.get(0));
            // Multiple sequence outputs remain attached results unless roles are explicitly supplied.
        }
        return slots;
    }
    private Map<String,Object> registerSources(String owner,String command,Map<String,Object> target,List<Map<String,Object>> received,Map<String,String> slots) throws Exception {
        String type=(String)target.get("data_type"),sample=(String)target.get("sample_id");boolean reads=List.of("meta","shortReads").contains(type);
        if(slots.isEmpty())return Map.of("status","results_only","message","Files attached as results. Provide source_slots to register multiple sequence files as sample inputs.");
        // Existing native source slots are preserved, without creating unused storage objects.
        if(reads) {
            var row=metadata.selectById(sample);
            for(var role:slots.keySet()) {
                String existing=role.equals("R1")?row.getFile1Id():row.getFile2Id();
                var source=received.stream().filter(f->slots.get(role).equals(f.get("source_path"))).findFirst().orElseThrow();
                if(existing!=null&&!existing.isBlank()&&!existing.equals(stable(owner+":"+command+":"+source.get("id"))))return Map.of("status","results_only","message","Existing sample sources preserved; pushed files are attached results.");
            }
        } else {
            String existing=fasta.selectById(sample).getFileId();
            var source=received.stream().filter(f->slots.get("genome").equals(f.get("source_path"))).findFirst().orElseThrow();
            if(existing!=null&&!existing.isBlank()&&!existing.equals(stable(owner+":"+command+":"+source.get("id"))))return Map.of("status","results_only","message","Existing genome preserved; pushed files are attached results.");
        }
        Map<String,String> ids=new HashMap<>();
        for(var slot:slots.entrySet()) {
            var source=received.stream().filter(f->slot.getValue().equals(f.get("source_path"))).findFirst().orElseThrow();
            String fileId=stable(owner+":"+command+":"+source.get("id"));ids.put(slot.getKey(),fileId);
            String resource="result:"+command+":"+source.get("id");Path path=delivery.resourcePath(owner,resource);
            String key="files/agent/"+fileId+"/"+source.get("name");
            if(files.getById(fileId)==null){
                storage.putFiles(bucket,Map.of(key,path));var file=new SampleFile();owned(file,owner);file.setId(fileId);file.setFileName((String)source.get("name"));file.setFileSize(((Number)source.get("size")).longValue());file.setBucket(bucket);file.setName(key);file.setObjectPath(bucket+"/"+key);file.setUploadTime(new Date());file.setUploadStatus("done");/* Native owner-specific aliases leave the global dedup key empty; receipt retains SHA-256. */ file.setContentHash(null);file.setIsExample(0);files.save(file);
            }
        }
        return transaction.execute(status->{
            if(reads){
                var row=metadata.selectOne(new QueryWrapper<Metadata>().eq("id",sample).eq("create_by",owner).last("FOR UPDATE"));
                if(row==null)throw new IllegalArgumentException("Sample unavailable.");
                boolean occupied=(row.getFile1Id()!=null&&!row.getFile1Id().isBlank()&&!row.getFile1Id().equals(ids.get("R1"))) || (row.getFile2Id()!=null&&!row.getFile2Id().isBlank()&&!row.getFile2Id().equals(ids.get("R2")));
                if(occupied)return Map.of("status","results_only","message","Existing sample sources preserved; pushed files are attached results.");
                row.setFile1Id(ids.get("R1"));if(ids.containsKey("R2"))row.setFile2Id(ids.get("R2"));metadata.updateById(row);
            } else {
                var row=fasta.selectOne(new QueryWrapper<FastaSample>().eq("id",sample).eq("create_by",owner).last("FOR UPDATE"));
                if(row==null)throw new IllegalArgumentException("Sample unavailable.");
                if(row.getFileId()!=null&&!row.getFileId().isBlank()&&!row.getFileId().equals(ids.get("genome")))return Map.of("status","results_only","message","Existing genome preserved; pushed files are attached results.");
                row.setFileId(ids.get("genome"));fasta.updateById(row);
            }
            return Map.of("status","registered","slots",ids);
        });
    }
}
