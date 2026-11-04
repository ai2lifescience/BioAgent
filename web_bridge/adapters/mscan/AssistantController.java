package com.mscan.web.controller.common;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.mscan.common.core.domain.AjaxResult;
import com.mscan.common.utils.SecurityUtils;
import com.mscan.database.domain.entity.*;
import com.mscan.database.mapper.IMetadataMapper;
import com.mscan.database.mapper.IFastSampleMapper;
import com.mscan.database.service.ISampleFileService;
import com.mscan.database.service.storage.ObjectStorageReader;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.web.bind.annotation.*;
import java.io.InputStream;
import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.*;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.security.MessageDigest;
import java.util.*;

/** Thin host adapter: current MSCAN principal -> generic BioAgent service API. */
@RestController
@RequestMapping("/assistant")
@ConditionalOnProperty(name="bioagent.enabled", havingValue="true")
public class AssistantController {
    @Value("${bioagent.url:http://127.0.0.1:8000}") private String base;
    @Value("${bioagent.public-url:}") private String publicUrl;
    @Value("${bioagent.site-id:mscan}") private String site;
    @Value("${bioagent.secret}") private String secret;
    @Value("${bioagent.origins:http://localhost:8848,http://127.0.0.1:8848}") private String origins;
    private record DownloadGrant(String owner,String resource,long expires) {}
    private final java.util.concurrent.ConcurrentHashMap<String,DownloadGrant> downloads=new java.util.concurrent.ConcurrentHashMap<>();
    private final ObjectMapper json;
    private final IMetadataMapper metadata;
    private final IFastSampleMapper fasta;
    private final ISampleFileService files;
    private final ObjectStorageReader storage;
    @org.springframework.beans.factory.annotation.Autowired(required=false) private AssistantDeliveryService delivery;
    @org.springframework.beans.factory.annotation.Autowired private NativeResultResources nativeFiles;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).followRedirects(HttpClient.Redirect.NEVER).build();

    public AssistantController(ObjectMapper json, IMetadataMapper metadata, IFastSampleMapper fasta,
                               ISampleFileService files, ObjectStorageReader storage) {
        this.json=json; this.metadata=metadata; this.fasta=fasta; this.files=files; this.storage=storage;
    }
    private String user() { return SecurityUtils.getUserId(); }
    private String origin(String value) {
        if (!Arrays.asList(origins.split(",")).contains(value)) throw new IllegalArgumentException("Website origin is not configured.");
        return value;
    }
    private HttpRequest.Builder request(String path) {
        return request(path,user());
    }
    HttpRequest.Builder request(String path,String subject) {
        if (secret.length()<32) throw new IllegalStateException("Assistant connector is not configured.");
        return HttpRequest.newBuilder(URI.create(base.replaceAll("/+$", "")+"/website/service/"+path))
                .timeout(path.equals("revoke")?Duration.ofSeconds(10):Duration.ofMinutes(5)).header("Authorization", "Bearer "+secret)
                .header("X-Website-Site", site).header("X-Website-Subject", subject);
    }
    Map<String,Object> decode(HttpResponse<InputStream> response) throws Exception {
        try (InputStream stream=response.body()) {
            byte[] data=stream.readNBytes(16*1024*1024+1);
            if(data.length>16*1024*1024) throw new IllegalStateException("Assistant response is too large.");
            Map<String,Object> result=json.readValue(data, new TypeReference<>() {});
            if(response.statusCode()/100!=2) throw new IllegalArgumentException(String.valueOf(result.getOrDefault("error", "Assistant request failed.")));
            return result;
        }
    }
    private Map<String,Object> call(String path, Map<String,Object> body) throws Exception {
        return callAs(user(),path,body);
    }
    Map<String,Object> callAs(String subject,String path,Map<String,Object> body) throws Exception {
        Map<String,Object> payload=new HashMap<>(body); payload.put("subject",subject);
        return decode(http.send(request(path,subject).header("Content-Type","application/json")
                .POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(payload))).build(), HttpResponse.BodyHandlers.ofInputStream()));
    }
    @org.springframework.context.event.EventListener
    public void onHostLogout(WebsiteLogoutEvent event) {
        if(event.userId()==null||event.userId().isBlank())return;
        downloads.entrySet().removeIf(e->event.userId().equals(e.getValue().owner()));
        try { callAs(event.userId(),"revoke",Map.of()); }
        catch(Exception error) {
            // Host logout must still complete if the independent agent is down.
            org.slf4j.LoggerFactory.getLogger(AssistantController.class).warn(
                    "Agent logout revocation unavailable; embedded login will expire automatically ({})",error.getClass().getSimpleName());
        }
    }
    @GetMapping("/config")
    public AjaxResult config(@RequestParam String origin) {
        URI host=URI.create(origin(origin));
        String browser=publicUrl.isBlank()?host.getScheme()+"://"+host.getHost()+":8000":publicUrl;
        return AjaxResult.success(Map.of("siteId",site,"agentUrl",browser));
    }
    @PostMapping({"/bootstrap","/ticket"})
    public AjaxResult bootstrap(@RequestBody Map<String,Object> body, HttpServletRequest request) throws Exception {
        String host=origin(String.valueOf(body.get("origin")));
        if(request.getHeader("Origin")!=null && !host.equals(request.getHeader("Origin"))) throw new IllegalArgumentException("Origin mismatch.");
        String operation=request.getRequestURI().endsWith("/ticket")?"ticket":"bootstrap";
        return AjaxResult.success(call(operation,Map.of("origin",host,"scope_key","workspace")));
    }
    @GetMapping("/results")
    public AjaxResult results() throws Exception { return AjaxResult.success(call("results",Map.of("scope_key","workspace"))); }
    @PostMapping("/logout")
    public AjaxResult logout() throws Exception { return AjaxResult.success(call("revoke",Map.of())); }
    @PostMapping("/download-ticket")
    public AjaxResult downloadTicket(@RequestBody Map<String,Object> body) throws Exception {
        return AjaxResult.success(call("artifact-ticket",Map.of("session_id",body.get("session_id"),"path",body.get("path"))));
    }

    private List<Map<String,Object>> sampleFiles(String owner,String sampleId,String dataType) {
        List<Map<String,Object>> result=new ArrayList<>();
        if("meta".equals(dataType)||"shortReads".equals(dataType)) {
            Metadata sample=metadata.selectById(sampleId);
            if(sample==null||!owner.equals(sample.getCreateBy())) throw new IllegalArgumentException("Sample not found.");
            addFile(owner,result,"R1",sample.getFile1Id()); addFile(owner,result,"R2",sample.getFile2Id());
        } else if("genomic".equals(dataType)||"synthetic".equals(dataType)) {
            FastaSample sample=fasta.selectById(sampleId);
            if(sample==null||!owner.equals(sample.getCreateBy())) throw new IllegalArgumentException("Sample not found.");
            addFile(owner,result,"genome",sample.getFileId());
        } else throw new IllegalArgumentException("Unknown sample type.");
        return result;
    }
    private void addFile(String owner,List<Map<String,Object>> result,String slot,String id) {
        if(id==null||id.isBlank())return;
        SampleFile file=files.getById(id);
        if(file==null||!owner.equals(file.getCreateBy()))return;
        result.add(Map.of("slot",slot,"id",id,"name",file.getFileName(),"size",file.getFileSize()==null?0:file.getFileSize()));
    }
    @GetMapping("/files")
    public AjaxResult files(@RequestParam String sampleId,@RequestParam(defaultValue="meta") String dataType) {
        return AjaxResult.success(sampleFiles(user(),sampleId,dataType));
    }
    @GetMapping("/resources")
    public AjaxResult resources(@RequestParam(defaultValue="") String sampleId,@RequestParam(defaultValue="0") int offset,@RequestParam(defaultValue="50") int limit) throws Exception {
        return AjaxResult.success(catalog(user(),sampleId,offset,limit));
    }
    Map<String,Object> catalog(String owner,String sampleId,int offset,int limit) throws Exception {
        List<Map<String,Object>> all=new ArrayList<>();
        var query=new com.baomidou.mybatisplus.core.conditions.query.QueryWrapper<Metadata>().eq("create_by",owner);
        if(!sampleId.isBlank())query.eq("id",sampleId);
        for(Metadata sample:metadata.selectList(query)) {
            String type="shortReads".equals(sample.getDataType())?"shortReads":"meta";
            all.add(Map.of("resource_id","sample:"+type+":"+sample.getId(),"sample_id",sample.getId(),"sample_name",sample.getSampleName(),"project_id",sample.getProjectId()==null?"":sample.getProjectId(),"data_type",type,"kind","sample","importable",false));
            for(var file:sampleFiles(owner,sample.getId(),type)) {var r=new HashMap<String,Object>(file);r.put("resource_id","source:"+type+":"+sample.getId()+":"+file.get("slot"));r.put("sample_id",sample.getId());r.put("sample_name",sample.getSampleName());r.put("data_type",type);r.put("kind","source_file");all.add(r);}
        }
        var fastaQuery=new com.baomidou.mybatisplus.core.conditions.query.QueryWrapper<FastaSample>().eq("create_by",owner);
        if(!sampleId.isBlank())fastaQuery.eq("id",sampleId);
        for(FastaSample sample:fasta.selectList(fastaQuery)) {
            String type="synthetic".equals(sample.getDataType())?"synthetic":"genomic";
            all.add(Map.of("resource_id","sample:"+type+":"+sample.getId(),"sample_id",sample.getId(),"sample_name",sample.getSampleName(),"project_id",sample.getProjectId()==null?"":sample.getProjectId(),"data_type",type,"kind","sample","importable",false));
            for(var file:sampleFiles(owner,sample.getId(),type)) {var r=new HashMap<String,Object>(file);r.put("resource_id","source:"+type+":"+sample.getId()+":"+file.get("slot"));r.put("sample_id",sample.getId());r.put("sample_name",sample.getSampleName());r.put("data_type",type);r.put("kind","source_file");all.add(r);}
        }
        Map<String,Map<String,Object>> samples=new HashMap<>();
        for(var entry:all)if("sample".equals(entry.get("kind")))samples.put((String)entry.get("sample_id"),entry);
        for(var file:nativeFiles.catalogMany(owner,samples.keySet())) {
            var resource=new HashMap<String,Object>(file);var sample=samples.get(file.get("sample_id"));
            resource.put("sample_name",sample.get("sample_name"));resource.put("project_id",sample.get("project_id"));resource.put("data_type",sample.get("data_type"));all.add(resource);
        }
        for(var receipt:delivery.results(owner,sampleId))for(Object value:(List<?>)receipt.get("files")) {
            var r=new HashMap<String,Object>((Map<String,Object>)value);var target=(Map<String,Object>)receipt.get("target");
            r.putAll(target);r.put("resource_id","result:"+receipt.get("id")+":"+r.get("id"));r.put("kind","analysis_output");all.add(r);
        }
        all.sort(Comparator.comparing(r->String.valueOf(r.get("resource_id"))));
        int start=Math.min(Math.max(0,offset),all.size()),end=Math.min(all.size(),start+Math.min(200,Math.max(1,limit)));
        return Map.of("resources",all.subList(start,end),"total",all.size(),"offset",start);
    }
    @GetMapping("/received")
    public AjaxResult received(@RequestParam(defaultValue="") String sampleId) throws Exception {return AjaxResult.success(delivery.results(user(),sampleId));}
    @PostMapping("/receive-share")
    public AjaxResult receiveShare(@RequestBody Map<String,Object> body) throws Exception {
        Map<String,Object> target=(Map<String,Object>)body.get("target");
        delivery.requireSample(user(),String.valueOf(target.get("sample_id")),String.valueOf(target.get("data_type")));
        return AjaxResult.success(call("receive-share",Map.of("code",body.get("code"),"target",target)));
    }
    @PostMapping("/received-ticket")
    public AjaxResult receivedTicket(@RequestBody Map<String,String> body) throws Exception {
        String resource=body.get("resource_id");
        if(resource.startsWith("native:"))nativeFiles.resolve(user(),resource);else delivery.resource(user(),resource);
        downloads.entrySet().removeIf(e->e.getValue().expires()<System.currentTimeMillis());
        if(downloads.size()>=1000)throw new IllegalStateException("Too many pending downloads.");
        String token=UUID.randomUUID().toString()+UUID.randomUUID();
        downloads.put(token,new DownloadGrant(user(),resource,System.currentTimeMillis()+60000));
        return AjaxResult.success(Map.of("token",token));
    }
    @GetMapping("/received-download/{token}")
    public void receivedDownload(@PathVariable String token,HttpServletResponse response) throws Exception {
        DownloadGrant grant=downloads.remove(token);
        if(grant==null||grant.expires()<System.currentTimeMillis()){response.setStatus(401);response.setContentType("application/json");response.setHeader("Cache-Control","no-store");response.getWriter().write("{\"error\":\"Download ticket expired or already used.\"}");return;}
        streamReceived(grant.owner(),grant.resource(),response);
    }
    @GetMapping("/received-file")
    public void receivedFile(@RequestParam String resource_id,HttpServletResponse response) throws Exception {
        streamReceived(user(),resource_id,response);
    }
    private long nativeSize(NativeResultResources.File file) throws Exception {
        if(file.data()!=null)return file.data().length;
        var head=storage.head(file.bucket(),file.key());
        if(!head.exists()||head.size()==null)throw new IllegalArgumentException("Native file unavailable.");
        return head.size();
    }
    private InputStream nativeStream(NativeResultResources.File file) throws Exception {
        return file.data()!=null?new java.io.ByteArrayInputStream(file.data()):storage.getInputStream(file.bucket(),file.key());
    }
    private void streamReceived(String owner,String resource_id,HttpServletResponse response) throws Exception {
        if(resource_id.startsWith("native:")) {
            var file=nativeFiles.resolve(owner,resource_id);long size=nativeSize(file);
            response.setContentType("application/octet-stream");response.setHeader("X-Content-Type-Options","nosniff");response.setHeader("Cache-Control","no-store");
            response.setHeader("Content-Disposition","attachment; filename*=UTF-8''"+URLEncoder.encode((String)file.descriptor().get("name"),StandardCharsets.UTF_8));response.setContentLengthLong(size);
            try(var input=nativeStream(file)){input.transferTo(response.getOutputStream());}return;
        }
        var file=delivery.resource(owner,resource_id);var path=delivery.resourcePath(owner,resource_id);
        response.setHeader("Referrer-Policy","no-referrer");
        response.setContentType("application/octet-stream");response.setHeader("X-Content-Type-Options","nosniff");response.setHeader("Cache-Control","no-store");
        response.setHeader("Content-Disposition","attachment; filename*=UTF-8''"+URLEncoder.encode((String)file.get("name"),StandardCharsets.UTF_8));
        response.setContentLengthLong(java.nio.file.Files.size(path));try(var input=java.nio.file.Files.newInputStream(path)){input.transferTo(response.getOutputStream());}
    }
    @PostMapping("/import-resource")
    public AjaxResult importResource(@RequestBody Map<String,String> body) throws Exception {
        String resource=body.get("resource_id");
        if(resource.startsWith("native:")) {
            var file=nativeFiles.resolve(user(),resource);long size=nativeSize(file);
            try(var input=nativeStream(file)) {
                return AjaxResult.success(transfer(input,body.get("session_id"),(String)file.descriptor().get("name"),size,resource,UUID.randomUUID().toString()));
            }
        }
        if(resource.startsWith("source:")) {
            String[] parts=resource.split(":");if(parts.length!=4)throw new IllegalArgumentException("Invalid resource.");
            return importFile(Map.of("sampleId",parts[2],"dataType",parts[1],"slot",parts[3],"session_id",body.get("session_id")));
        }
        var file=delivery.resource(user(),resource);var path=delivery.resourcePath(user(),resource);
        try(var input=java.nio.file.Files.newInputStream(path)) {
            return AjaxResult.success(transfer(input,body.get("session_id"),(String)file.get("name"),java.nio.file.Files.size(path),resource,(String)file.get("sha256")));
        }
    }
    private Map<String,Object> transfer(InputStream input,String session,String filename,long size,String resource,String revision) throws Exception {
        var upload=call("uploads",Map.of("session_id",session,"filename",filename,"size",size,"resource_id",resource,"revision",revision));
        if(upload.get("file")!=null)return (Map<String,Object>)upload.get("file");
        String id=(String)upload.get("upload_id");long offset=((Number)upload.getOrDefault("offset",0)).longValue();
        MessageDigest digest=MessageDigest.getInstance("SHA-256");long skip=offset;
        while(skip>0){byte[] chunk=input.readNBytes((int)Math.min(skip,65536));if(chunk.length==0)throw new IOException("Source changed.");digest.update(chunk);skip-=chunk.length;}
        while(true){byte[] chunk=input.readNBytes(8*1024*1024);if(chunk.length==0)break;digest.update(chunk);
            var state=decode(http.send(request("uploads/"+id).header("Upload-Offset",String.valueOf(offset)).method("PATCH",HttpRequest.BodyPublishers.ofByteArray(chunk)).build(),HttpResponse.BodyHandlers.ofInputStream()));offset=((Number)state.get("offset")).longValue();}
        if(offset!=size)throw new IOException("Source changed.");
        return call("uploads/"+id+"/complete",Map.of("sha256",HexFormat.of().formatHex(digest.digest())));
    }
    Map<String,Object> pullCommand(String owner,String session,String command,String resource) throws Exception {
        if(resource.startsWith("native:")) {
            var file=nativeFiles.resolve(owner,resource);long size=nativeSize(file);
            // A fresh revision prevents stale cache hits if a native object was replaced in place.
            try(var input=nativeStream(file)) {
                return transferCommand(owner,command,input,session,(String)file.descriptor().get("name"),size,resource,UUID.randomUUID().toString());
            }
        }
        if(resource.startsWith("source:")) {
            String[] parts=resource.split(":");if(parts.length!=4)throw new IllegalArgumentException("Invalid resource.");
            var selected=sampleFiles(owner,parts[2],parts[1]).stream().filter(f->f.get("slot").equals(parts[3])).findFirst().orElseThrow(()->new IllegalArgumentException("Source not found."));
            var file=files.getById((String)selected.get("id"));var head=storage.head(file.getBucket(),file.getName());
            if(!head.exists()||head.size()==null)throw new IllegalArgumentException("Source unavailable.");
            try(var input=storage.getInputStream(file.getBucket(),file.getName())) {
                return transferCommand(owner,command,input,session,file.getFileName(),head.size(),resource,file.getId()+":"+file.getUpdateTime()+":"+String.valueOf(file.getContentHash())+":"+head.size());
            }
        }
        var file=delivery.resource(owner,resource);var path=delivery.resourcePath(owner,resource);
        try(var input=java.nio.file.Files.newInputStream(path)) {return transferCommand(owner,command,input,session,(String)file.get("name"),java.nio.file.Files.size(path),resource,(String)file.get("sha256"));}
    }
    private Map<String,Object> transferCommand(String owner,String command,InputStream input,String session,String filename,long size,String resource,String revision) throws Exception {
        var upload=callAs(owner,"uploads",Map.of("command_id",command,"session_id",session,"filename",filename,"size",size,"resource_id",resource,"revision",revision));
        if(upload.get("file")!=null)return (Map<String,Object>)upload.get("file");
        String id=(String)upload.get("upload_id");long offset=((Number)upload.getOrDefault("offset",0)).longValue();
        MessageDigest digest=MessageDigest.getInstance("SHA-256");long skip=offset;
        while(skip>0){byte[] chunk=input.readNBytes((int)Math.min(skip,65536));if(chunk.length==0)throw new IOException("Source changed.");digest.update(chunk);skip-=chunk.length;}
        while(true){byte[] chunk=input.readNBytes(8*1024*1024);if(chunk.length==0)break;digest.update(chunk);
            var state=decode(http.send(request("uploads/"+id,owner).header("Upload-Offset",String.valueOf(offset)).method("PATCH",HttpRequest.BodyPublishers.ofByteArray(chunk)).build(),HttpResponse.BodyHandlers.ofInputStream()));offset=((Number)state.get("offset")).longValue();}
        if(offset!=size)throw new IOException("Source changed.");
        return callAs(owner,"uploads/"+id+"/complete",Map.of("sha256",HexFormat.of().formatHex(digest.digest())));
    }
    @PostMapping("/import")
    public AjaxResult importFile(@RequestBody Map<String,String> body) throws Exception {
        String sample=body.get("sampleId"), type=body.getOrDefault("dataType","meta"), slot=body.get("slot");
        Map<String,Object> selected=sampleFiles(user(),sample,type).stream().filter(f->f.get("slot").equals(slot)).findFirst().orElseThrow(()->new IllegalArgumentException("Sample file not found."));
        SampleFile file=files.getById((String)selected.get("id"));
        ObjectStorageReader.ObjectHead head=storage.head(file.getBucket(),file.getName());
        if(!head.exists()||head.size()==null) throw new IllegalArgumentException("Source file unavailable.");
        // MSCAN's content_hash is an opaque deduplication key: example records
        // hash the object key, while ordinary uploads may store MD5.
        String revision=String.valueOf(file.getContentHash())+":"+file.getUpdateTime()+":"+head.size();
        Map<String,Object> upload=call("uploads",Map.of("session_id",body.get("session_id"),"filename",file.getFileName(),"size",head.size(),"resource_id",sample+":"+slot,"revision",revision));
        String id=(String)upload.get("upload_id");
        if(upload.get("file")!=null)return AjaxResult.success(upload.get("file"));
        try(InputStream input=storage.getInputStream(file.getBucket(),file.getName())) {
            long offset=((Number)upload.getOrDefault("offset",0)).longValue();
            MessageDigest digest=MessageDigest.getInstance("SHA-256");
            long remaining=offset;
            while(remaining>0){byte[] part=input.readNBytes((int)Math.min(remaining,65536));if(part.length==0)throw new IllegalStateException("Source file changed.");digest.update(part);remaining-=part.length;}
            while(true) {
                byte[] chunk=input.readNBytes(8*1024*1024); if(chunk.length==0)break;
                digest.update(chunk);
                Map<String,Object> state=decode(http.send(request("uploads/"+id).header("Content-Type","application/octet-stream")
                        .header("Upload-Offset",String.valueOf(offset)).method("PATCH",HttpRequest.BodyPublishers.ofByteArray(chunk)).build(),HttpResponse.BodyHandlers.ofInputStream()));
                offset=((Number)state.get("offset")).longValue();
            }
            if(offset!=head.size())throw new IllegalStateException("Source file changed during transfer.");
            String sha256=HexFormat.of().formatHex(digest.digest());
            return AjaxResult.success(call("uploads/"+id+"/complete",Map.of("sha256",sha256)));
        } catch(Exception error) {
            try {call("uploads/"+id+"/cancel",Map.of());}catch(Exception ignored){}
            throw error;
        }
    }
    @GetMapping("/artifact")
    public void artifact(@RequestParam String session_id,@RequestParam String path,HttpServletRequest incoming,HttpServletResponse outgoing) throws Exception {
        String query="artifact?session_id="+URLEncoder.encode(session_id,StandardCharsets.UTF_8)+"&path="+URLEncoder.encode(path,StandardCharsets.UTF_8);
        HttpRequest.Builder req=request(query).GET();
        if(incoming.getHeader("Range")!=null) req.header("Range",incoming.getHeader("Range"));
        HttpResponse<InputStream> response=http.send(req.build(),HttpResponse.BodyHandlers.ofInputStream());
        outgoing.setStatus(response.statusCode());
        outgoing.setHeader("Cache-Control","no-store"); outgoing.setHeader("X-Content-Type-Options","nosniff");
        outgoing.setContentType(response.headers().firstValue("Content-Type").orElse("application/octet-stream"));
        for(String header:List.of("Content-Length","Content-Range","Accept-Ranges"))response.headers().firstValue(header).ifPresent(v->outgoing.setHeader(header,v));
        String name=path.substring(path.lastIndexOf('/')+1);
        outgoing.setHeader("Content-Disposition","attachment; filename*=UTF-8''"+URLEncoder.encode(name,StandardCharsets.UTF_8));
        try(InputStream input=response.body()) { input.transferTo(outgoing.getOutputStream()); }
    }
    @ExceptionHandler({IllegalArgumentException.class,IllegalStateException.class})
    public AjaxResult invalid(RuntimeException error) { return AjaxResult.error(error.getMessage()); }
}
