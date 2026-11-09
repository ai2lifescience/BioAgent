package com.mscan.web.controller.common;

import com.google.gson.JsonObject;
import com.mscan.database.domain.entity.SampleTaskInfo;
import com.mscan.database.service.*;
import com.mscan.database.service.storage.ObjectStorageReader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.nio.file.Path;
import java.nio.charset.StandardCharsets;
import java.util.*;

/** Orchestrates owned result imports, transactions, retries and per-job outcomes. */
@Service
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class ResultImportService {
    private final ResultImporterRegistry registry;
    private final QcResultImporter qcImport;
    private final ISampleTaskInfoService tasks;
    private final ObjectStorageReader storage;
    private final TransactionTemplate tx;
    @Value("${minio.bucketName}") private String bucket;
    public ResultImportService(ISampleTaskInfoService tasks,ObjectStorageReader storage,
            PlatformTransactionManager manager,ResultImporterRegistry registry,QcResultImporter qcImport) {
        this.tasks=tasks;this.storage=storage;this.tx=new TransactionTemplate(manager);this.registry=registry;this.qcImport=qcImport;
    }
    /** Import a newly received file bundle into native records. */
    public void importReceipt(String owner,String sample,String type,String id,Path dir,
            Map<String,Object> receipt,List<Map<String,Object>> previousReceipts) throws Exception {
        var saved=(List<Map<String,Object>>)receipt.get("files");
        Map<String,Long> qc=new HashMap<>();
        Map<String,Object> qcSummary=null;
        for(var file:saved)if("summary".equals(QcResultImporter.role(file)) &&
            (qcSummary==null || completedAt(resultOrigin(file,receipt))>completedAt(resultOrigin(qcSummary,receipt))))qcSummary=file;
        String qcJob=qcSummary==null?"":String.valueOf(((Map<?,?>)qcSummary.getOrDefault("pipeline_result",Map.of())).getOrDefault("job_id",null));
        if(qcSummary!=null)qc.putAll(QcResultImporter.readCounts(dir.resolve((String)qcSummary.get("id"))));
        receipt.put("qc",qc);
        receipt.put("native_qc_job",qcJob);
        // Preserve newer QC results when importing an older delivery.
        double completed=completedAt(qcSummary==null?receipt:resultOrigin(qcSummary,receipt));
        receipt.put("qc_completed_at",completed);
        boolean newest=previousReceipts.stream().noneMatch(r -> !((Map<?,?>)r.getOrDefault("qc",Map.of())).isEmpty()
            && ((Number)r.getOrDefault("qc_completed_at",completedAt(r))).doubleValue()>completed);
        boolean applyQc=!qc.isEmpty()&&List.of("meta","shortReads").contains(type)&&newest;
        receipt.put("native_qc_applied",applyQc);
        if(applyQc) {
            var qcFiles=saved.stream().filter(f->qcJob.equals(String.valueOf(((Map<?,?>)f.getOrDefault("pipeline_result",Map.of())).get("job_id")))).toList();
            qcImport.apply(owner,sample,id,dir,qcFiles,qc);
        }
        importResults(owner,sample,type,id,dir,receipt);
    }
    /** Retry native result handlers without applying committed QC a second time. */
    public void importResults(String owner,String sample,String type,String id,Path dir,Map<String,Object> receipt) {
        var reports=apply(owner,sample,type,id,dir,(List<Map<String,Object>>)receipt.get("files"));
        for(var report:reports)if("qc".equals(report.get("state"))) {
            boolean applied=Boolean.TRUE.equals(receipt.get("native_qc_applied"))&&report.get("job_id").equals(receipt.get("native_qc_job"));
            report.put("state",applied?"imported":"not_imported");
            report.put("program","qc");report.put("message",applied?"Native QC imported.":"QC was not applied; inspect format, sample type and newer results.");
        }
        receipt.put("native_imports",reports);
        receipt.put("native_import_failed",reports.stream().anyMatch(r->"failed".equals(r.get("state"))));
    }
    private static Map<String,Object> resultOrigin(Map<String,Object> file,Map<String,Object> fallback) {
        return file.get("pipeline_result") instanceof Map<?,?> origin?(Map<String,Object>)origin:fallback;
    }
    private static double completedAt(Map<String,Object> value) {
        Object raw=value.getOrDefault("completed_at",value.get("created_at"));
        if(raw instanceof Number number)return number.doubleValue();
        try{return Double.parseDouble(String.valueOf(raw));}
        catch(NumberFormatException ignored){try{return java.time.Instant.parse(String.valueOf(raw)).toEpochMilli()/1000.0;}catch(Exception invalid){return 0;}}
    }
    public List<Map<String,Object>> apply(String owner,String sample,String type,String delivery,Path dir,List<Map<String,Object>> files) {
        Map<String,List<Map<String,Object>>> groups=new LinkedHashMap<>();
        for(var file:files)if(file.get("pipeline_result") instanceof Map<?,?> provenance) {
            String job=String.valueOf(provenance.get("job_id"));
            if(!job.matches("[a-f0-9]{32}"))throw new IllegalArgumentException("Invalid result job identity.");
            groups.computeIfAbsent(job,k->new ArrayList<>()).add(file);
        }
        List<Map<String,Object>> reports=new ArrayList<>();
        for(var entry:groups.entrySet())reports.add(importJob(owner,sample,type,delivery,dir,entry.getKey(),entry.getValue()));
        return reports;
    }
    private Map<String,Object> importJob(String owner,String sample,String type,String delivery,Path dir,String job,List<Map<String,Object>> files) {
        Map<String,Object> report=new LinkedHashMap<>();report.put("job_id",job);report.put("files_delivered",true);
        report.put("generic_import",Map.of("state","imported","artifact_count",files.size(),
            "access","Search or pull the attached sample files; native records are a separate outcome."));
        var provenance=(Map<String,Object>)files.get(0).get("pipeline_result");report.put("pipeline",provenance.getOrDefault("pipeline_name",""));
        Set<String> formats=new HashSet<>();Map<String,Map<String,Object>> outputs=new LinkedHashMap<>();
        for(var file:files) {
            var origin=(Map<String,Object>)file.get("pipeline_result");String key=String.valueOf(origin.getOrDefault("output_key",""));
            int dot=key.lastIndexOf('.');if(dot<1)continue;formats.add(key.substring(0,dot));
            if(outputs.put(key.substring(dot+1),file)!=null)return status(report,"unsupported","Duplicate output roles; select one complete job.");
        }
        if(formats.size()!=1)return status(report,"unsupported","No unambiguous native result format; files remain available.");
        String format=formats.iterator().next();report.put("format",format);
        if(format.equals("ReadQc")||format.equals("MetagenomicQc"))return status(report,"qc","Handled by the QC importer.");
        ResultImporterRegistry.Rule rule=registry.find(format);
        if(rule==null)return status(report,"unsupported","MSCAN has no registered importer for this result format; files remain available.");
        report.put("program",rule.program());
        if(!rule.types().contains(type))return status(report,"incompatible_sample_type","This result format does not match the destination sample type.");
        if(!outputs.keySet().containsAll(rule.required())) {
            var missing=new TreeSet<>(rule.required());missing.removeAll(outputs.keySet());report.put("missing_outputs",missing);
            return status(report,"incomplete","Select the complete pipeline bundle to import native results.");
        }
        String id=UUID.nameUUIDFromBytes((owner+":"+sample+":"+delivery+":"+job).getBytes(StandardCharsets.UTF_8)).toString().replace("-","");
        try {
            var previous=tasks.getById(id);
            if(previous!=null&&"Succeeded".equals(previous.getTaskStatus()))return status(report,"imported","Native result already imported.");
            Date completed;
            try {completed=Date.from(java.time.Instant.parse(String.valueOf(provenance.get("completed_at"))));}
            catch(Exception invalid) {completed=new Date(0);}
            final Date resultTime=completed;
            Map<String,Path> objects=new LinkedHashMap<>();JsonObject values=new JsonObject();
            for(var entry:outputs.entrySet()) {
                String fileId=String.valueOf(entry.getValue().get("id"));
                if(!fileId.matches("[a-f0-9]{64}"))throw new IllegalArgumentException("Invalid received file identity.");
                String name=Path.of(String.valueOf(entry.getValue().get("name"))).getFileName().toString();
                String key="files/agent-analysis/"+id+"/"+fileId+"/"+name;
                objects.put(key,dir.resolve(fileId));values.addProperty(format+"."+entry.getKey(),"s3://"+bucket+"/"+key);
            }
            storage.putFiles(bucket,objects);
            JsonObject metadata=new JsonObject();metadata.add("outputs",values);
            tx.executeWithoutResult(state->{
                var later=tasks.list(new com.baomidou.mybatisplus.core.conditions.query.QueryWrapper<SampleTaskInfo>()
                    .eq("sample_pathogen_id",sample).eq("method",rule.program()).in("task_status",List.of("Succeeded","Successed"))
                    .gt("create_time",resultTime));
                if(!later.isEmpty())throw new NewerResult();
                var task=new SampleTaskInfo();task.setId(id);task.setSamplePathogenId(sample);task.setTaskId("bioagent:"+id);
                task.setMethod(rule.program());task.setSeqType(type.equals("meta")||type.equals("shortReads")?"meta":"genomic");
                // A terminal state keeps MSCAN's remote poller away from an imported result.
                task.setTaskStatus("Succeeded");task.setCreateBy(owner);task.setUpdateBy(owner);task.setCreateTime(resultTime);task.setUpdateTime(new Date());task.setDelFlag("0");
                tasks.saveOrUpdate(task);
                NativeImportContext.run(task.getTaskId(),metadata,()->rule.importer().accept(task));
                task.setTaskStatus("Succeeded");tasks.updateById(task);
            });
            return status(report,"imported","Native result imported.");
        } catch(NewerResult error) {
            return status(report,"superseded","A newer native result was preserved; these files remain available.");
        } catch(Exception error) {
            report.putAll(ImportFailure.describe(error));
            report.put("state","failed");return report;
        }
    }
    private static class NewerResult extends RuntimeException {}
    private static Map<String,Object> status(Map<String,Object> report,String state,String message) {
        report.put("state",state);report.put("message",message);return report;
    }
}
