package com.mscan.web.controller.common;

import com.mscan.database.domain.entity.*;
import com.mscan.database.mapper.ISampleInfoMapper;
import com.mscan.database.service.*;
import com.mscan.database.service.storage.ObjectStorageReader;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;
import java.nio.file.Path;
import java.nio.file.Files;
import java.io.IOException;
import java.util.*;

/** Map received QC outputs into MSCAN's own durable QC/status records. */
@Service
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class QcResultImporter {
    static Map<String,Long> readCounts(Path path) throws Exception {
        if(Files.size(path)>65536)throw new IOException("Invalid QC summary.");
        Map<String,Long> values=new HashMap<>();
        var lines=Files.readAllLines(path).stream().filter(line->!line.isBlank()).toList();
        if(!lines.isEmpty()&&Arrays.asList(lines.get(0).split("\t",-1)).contains("raw_reads")) {
            if(lines.size()!=2)throw new IOException("QC summary must describe exactly one sample; split multi-sample results before importing.");
            var columns=Arrays.asList(lines.get(0).split("\t",-1));String[] row=lines.get(1).split("\t",-1);
            var mapping=Map.of("raw_reads","InputReads","reads_before_host","ReadsAfterQC","final_clean_reads","ReadsAfterHostRemoval",
                "quality_dropped_reads","QualityDroppedReads","univec_core_hit_reads","UnivecCoreHitReads","host_reads","HostReads");
            for(var field:mapping.entrySet()) {
                int index=columns.indexOf(field.getKey());if(index<0||index>=row.length)throw new IOException("Missing QC column: "+field.getKey());
                long count=Long.parseLong(row[index]);if(count<0)throw new IOException("Negative QC count.");values.put(field.getValue(),count);
            }
        } else for(String line:lines) {
            String[] fields=line.split("\t");
            if(fields.length==2&&List.of("InputReads","ReadsAfterQC","ReadsAfterHostRemoval").contains(fields[0])) {
                long count=Long.parseLong(fields[1]);if(count<0)throw new IOException("Negative QC count.");values.put(fields[0],count);
            }
        }
        if(!values.keySet().containsAll(List.of("InputReads","ReadsAfterQC","ReadsAfterHostRemoval"))||values.get("InputReads")<values.get("ReadsAfterQC")||values.get("ReadsAfterQC")<values.get("ReadsAfterHostRemoval"))throw new IOException("Invalid QC counts.");
        return values;
    }
    static String role(Map<String,Object> file) {
        if(file.get("pipeline_result") instanceof Map<?,?> origin) {
            String key=String.valueOf(origin.get("output_key"));
            if(key.startsWith("ReadQc.")||key.startsWith("MetagenomicQc."))return switch(key.substring(key.lastIndexOf('.')+1)) {
                case "clean_r1" -> "r1";
                case "clean_r2" -> "r2";
                case "qc_counts", "qc_summary" -> "summary";
                case "multiqc_html" -> "multiqc";
                default -> "";
            };
        }
        String name=String.valueOf(file.get("name"));
        if(name.matches("clean[._][Rr]1\\.(fq|fastq)(\\.gz)?"))return "r1";
        if(name.matches("clean[._][Rr]2\\.(fq|fastq)(\\.gz)?"))return "r2";
        if(name.equals("qc_counts.tsv")||name.endsWith("input_qc_counts.tsv"))return "summary";
        return name.equals("multiqc_report.html")?"multiqc":"";
    }
    private final ISampleInfoMapper info;
    private final IQcResultRecordService records;
    private final IMetadataStatusService statuses;
    private final ObjectStorageReader storage;
    private final TransactionTemplate tx;
    @Value("${minio.bucketName}") private String bucket;
    public QcResultImporter(ISampleInfoMapper info,IQcResultRecordService records,IMetadataStatusService statuses,ObjectStorageReader storage,PlatformTransactionManager tx) {
        this.info=info;this.records=records;this.statuses=statuses;this.storage=storage;this.tx=new TransactionTemplate(tx);
    }
    void apply(String owner,String sample,String delivery,Path dir,List<Map<String,Object>> files,Map<String,Long> qc) throws Exception {
        Map<String,Path> objects=new LinkedHashMap<>();Map<String,String> paths=new HashMap<>();
        for(var file:files) {
            String name=(String)file.get("name"),role=role(file);
            if(role.isEmpty())continue;
            String key="files/agent-qc/"+delivery+"/"+name;
            objects.put(key,dir.resolve((String)file.get("id")));paths.put(role,"s3://"+bucket+"/"+key);
        }
        if(!objects.isEmpty())storage.putFiles(bucket,objects);
        tx.executeWithoutResult(status->{
            var existing=records.getById(delivery);
            if(existing==null) {
                var record=new QcResultRecord();record.setId(delivery);record.setSampleId(sample);
                record.setTaskId("bioagent:"+delivery);record.setQcProgram("read_qc");record.setRunStatus(2);
                record.setOptionsJson("{\"source\":\"bioagent_import\"}");record.setSummaryPath(paths.get("summary"));
                record.setCleanR1Path(paths.get("r1"));record.setCleanR2Path(paths.get("r2"));
                record.setLayout(paths.containsKey("r2")?"PE":"SE");record.setRawReads(qc.get("InputReads"));
                record.setReadsBeforeHost(qc.get("ReadsAfterQC"));record.setFinalCleanReads(qc.get("ReadsAfterHostRemoval"));
                record.setQualityDroppedReads(qc.get("QualityDroppedReads"));record.setUnivecCoreHitReads(qc.get("UnivecCoreHitReads"));record.setHostReads(qc.get("HostReads"));
                record.setCreateBy(owner);record.setUpdateBy(owner);record.setCreateTime(new Date());record.setUpdateTime(new Date());record.setDelFlag("0");
                records.save(record);
            } else if(!sample.equals(existing.getSampleId())||!owner.equals(existing.getCreateBy()))throw new IllegalArgumentException("QC receipt ownership mismatch.");
            SampleInfo row=info.selectById(sample);
            if(row==null){row=new SampleInfo();row.setSampleId(sample);row.setCreateBy(owner);row.setUpdateBy(owner);info.insert(row);}
            var changes=new SampleInfo();changes.setSampleId(sample);changes.setInputReads(qc.get("InputReads"));
            changes.setReadsAfterQC(qc.get("ReadsAfterQC"));changes.setReadsAfterHostRemoval(qc.get("ReadsAfterHostRemoval"));changes.setCreateBy(owner);changes.setUpdateBy(owner);
            if(paths.containsKey("multiqc"))changes.setMultiqcHtml(paths.get("multiqc"));
            info.updateById(changes);
            statuses.saveOrUpdateRunStatus(sample,"qc",2,owner);
        });
    }
}
