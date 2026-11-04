package com.mscan.web.controller.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mscan.database.mapper.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.net.*;
import java.net.http.*;
import java.io.*;
import java.time.Duration;
import java.security.MessageDigest;
import java.util.*;

/** Site adapter: durable files and receipts with owner-checked sample attachment. */
@Service
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class AssistantDeliveryService {
    @Value("${bioagent.url:http://127.0.0.1:8000}") private String base;
    @Value("${bioagent.site-id:mscan}") private String site;
    @Value("${bioagent.secret}") private String secret;
    @Value("${bioagent.results-root:./data/agent-results}") private String root;
    private final ObjectMapper json;
    private final IMetadataMapper metadata;
    private final IFastSampleMapper fasta;
    @org.springframework.beans.factory.annotation.Autowired private ResultImportService resultImport;
    @org.springframework.beans.factory.annotation.Autowired private TransferLocks locks;
    private final HttpClient http=HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(10)).build();
    public AssistantDeliveryService(ObjectMapper json,IMetadataMapper metadata,IFastSampleMapper fasta) {
        this.json=json;this.metadata=metadata;this.fasta=fasta;
    }
    private HttpRequest.Builder request(String path) {
        return HttpRequest.newBuilder(URI.create(base.replaceAll("/+$", "")+"/website/service/"+path))
            .timeout(Duration.ofMinutes(20)).header("Authorization","Bearer "+secret).header("X-Website-Site",site);
    }
    private Map<String,Object> call(String path,Map<String,Object> body) throws Exception {
        var r=http.send(request(path).header("Content-Type","application/json").POST(HttpRequest.BodyPublishers.ofString(json.writeValueAsString(body))).build(),HttpResponse.BodyHandlers.ofString());
        if(r.statusCode()/100!=2)throw new IOException("Agent service HTTP "+r.statusCode());
        return json.readValue(r.body(),Map.class);
    }
    public void requireSample(String owner,String sample,String type) {
        if(List.of("meta","shortReads").contains(type)) {
            var row=metadata.selectById(sample);
            if(row==null||!owner.equals(row.getCreateBy()))throw new IllegalArgumentException("Sample not found.");
        } else if(List.of("genomic","synthetic").contains(type)) {
            var row=fasta.selectById(sample);
            if(row==null||!owner.equals(row.getCreateBy()))throw new IllegalArgumentException("Sample not found.");
        } else throw new IllegalArgumentException("Unknown sample type.");
    }
    private Path folder(String id) {
        if(!id.matches("[a-f0-9]{32}"))throw new IllegalArgumentException("Invalid delivery.");
        return Path.of(root).toAbsolutePath().normalize().resolve(id);
    }
    @Scheduled(fixedDelayString="${bioagent.delivery-poll-ms:5000}")
    public synchronized void poll() {
        try {
            var pending=call("deliveries",Map.of());
            for(Object value:(List<?>)pending.getOrDefault("deliveries",List.of())) {
                Map<String,Object> item=(Map<String,Object>)value;
                Map<String,Object> ack=new HashMap<>();ack.put("id",item.get("id"));ack.put("lease",item.get("lease"));
                try {receive(item);ack.put("ok",true);ack.put("receipt",Map.of("id",item.get("id")));}
                catch(Exception error){ack.put("ok",false);ack.put("error",error.getClass().getSimpleName()+": "+error.getMessage());}
                call("delivery-ack",ack);
            }
        } catch(Exception error) {
            org.slf4j.LoggerFactory.getLogger(getClass()).debug("Agent result delivery unavailable: {}",error.getClass().getSimpleName());
        }
    }
    void receive(Map<String,Object> item) throws Exception { receive(item,"delivery-artifact"); }
    void receive(Map<String,Object> item,String artifactEndpoint) throws Exception {
        var target=(Map<String,Object>)item.get("target");
        // Same lock order as explicit pushes. Reentrant when called by a push worker.
        try(var sampleLock=locks.sample((String)item.get("subject"),(String)target.get("sample_id"));
                var receiptLock=locks.receipt((String)item.get("id"))) {
            receiveLocked(item,artifactEndpoint);
        }
    }
    private void receiveLocked(Map<String,Object> item,String artifactEndpoint) throws Exception {
        String id=(String)item.get("id"),owner=(String)item.get("subject");
        Map<String,Object> target=(Map<String,Object>)item.get("target");
        String sample=(String)target.get("sample_id"),type=(String)target.get("data_type");
        requireSample(owner,sample,type);
        Path dir=folder(id);Files.createDirectories(dir);
        Files.setPosixFilePermissions(dir.getParent(),java.nio.file.attribute.PosixFilePermissions.fromString("rwx------"));
        Files.setPosixFilePermissions(dir,java.nio.file.attribute.PosixFilePermissions.fromString("rwx------"));
        if(Files.exists(dir.resolve("receipt.json"))) {
            var existing=json.readValue(dir.resolve("receipt.json").toFile(),Map.class);
            if(Boolean.TRUE.equals(existing.get("native_import_failed"))) {
                resultImport.importResults(owner,sample,type,id,dir,existing);
                json.writeValue(dir.resolve("receipt.part").toFile(),existing);
                Files.move(dir.resolve("receipt.part"),dir.resolve("receipt.json"),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
                if(Boolean.TRUE.equals(existing.get("native_import_failed")))throw new IOException("Files delivered; native import failed. Check the received receipt, then retry.");
            }
            return; // Lost acknowledgement, already committed.
        }
        List<Map<String,Object>> saved=new ArrayList<>();
        for(Object value:(List<?>)item.getOrDefault("files",List.of())) {
            Map<String,Object> f=(Map<String,Object>)value;
            String source=String.valueOf(f.getOrDefault("workspace_path",f.get("path")));
            String key=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(source.getBytes(StandardCharsets.UTF_8)));
            Path part=dir.resolve(key+".part"),destination=dir.resolve(key);
            String query=artifactEndpoint+"?id="+id+"&path="+URLEncoder.encode(source,StandardCharsets.UTF_8);
            var response=http.send(request(query).GET().build(),HttpResponse.BodyHandlers.ofInputStream());
            MessageDigest digest=MessageDigest.getInstance("SHA-256");long size;
            try(InputStream in=new java.security.DigestInputStream(response.body(),digest)) {
                if(response.statusCode()/100!=2)throw new IOException("Artifact HTTP "+response.statusCode());
                size=Files.copy(in,part,StandardCopyOption.REPLACE_EXISTING);
            }
            if(f.get("size") instanceof Number && size!=((Number)f.get("size")).longValue())throw new IOException("Artifact size mismatch.");
            String sha=HexFormat.of().formatHex(digest.digest());
            if(f.get("sha256") instanceof String && !sha.equals(f.get("sha256")))throw new IOException("Artifact checksum mismatch.");
            Files.move(part,destination,StandardCopyOption.REPLACE_EXISTING);
            String name=source.substring(source.lastIndexOf('/')+1);
            var savedFile=new HashMap<String,Object>(Map.of("id",key,"name",name,"size",size,"sha256",sha,"source_path",source));
            if(f.get("pipeline_result") instanceof Map<?,?>)savedFile.put("pipeline_result",f.get("pipeline_result"));
            saved.add(savedFile);
        }
        Map<String,Object> receipt=new HashMap<>(item);receipt.remove("lease");receipt.put("files",saved);
        resultImport.importReceipt(owner,sample,type,id,dir,receipt,results(owner,sample));
        json.writeValue(dir.resolve("receipt.part").toFile(),receipt);
        Files.move(dir.resolve("receipt.part"),dir.resolve("receipt.json"),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
        if(Boolean.TRUE.equals(receipt.get("native_import_failed")))throw new IOException("Files delivered; native import failed. Check the received receipt, then retry.");
    }
    public List<Map<String,Object>> results(String owner,String sample) throws Exception {
        List<Map<String,Object>> result=new ArrayList<>();Path base=Path.of(root).toAbsolutePath();if(!Files.isDirectory(base))return result;
        try(var folders=Files.list(base)) {
            for(Path dir:folders.toList()) {
                Path file=dir.resolve("receipt.json");if(!Files.isRegularFile(file))continue;
                Map<String,Object> r=json.readValue(file.toFile(),Map.class);Map<String,Object> target=(Map<String,Object>)r.get("target");
                if(!owner.equals(r.get("subject"))||(!sample.isBlank()&&!sample.equals(target.get("sample_id"))))continue;
                try{requireSample(owner,(String)target.get("sample_id"),(String)target.get("data_type"));}catch(IllegalArgumentException ignored){continue;}
                result.add(r);
            }
        }
        result.sort(Comparator.comparing(r->String.valueOf(r.get("created_at")),Comparator.reverseOrder()));return result;
    }
    public Map<String,Object> resource(String owner,String id) throws Exception {
        String[] parts=id.split(":");if(parts.length!=3||!parts[0].equals("result"))throw new IllegalArgumentException("Invalid resource.");
        for(var r:results(owner,""))if(parts[1].equals(r.get("id")))for(Object v:(List<?>)r.get("files")) {
            Map<String,Object> f=(Map<String,Object>)v;if(parts[2].equals(f.get("id")))return f;
        }
        throw new IllegalArgumentException("Result not found.");
    }
    public Path resourcePath(String owner,String id) throws Exception {
        Map<String,Object> f=resource(owner,id);return folder(id.split(":")[1]).resolve((String)f.get("id"));
    }
}
