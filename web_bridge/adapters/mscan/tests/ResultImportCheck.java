package com.mscan.web.controller.common;

import com.mscan.database.service.*;
import org.springframework.transaction.PlatformTransactionManager;
import java.lang.reflect.Proxy;
import java.nio.file.*;
import java.util.*;

/** Verify receipt behavior across the transfer/importer boundary without database writes. */
public class ResultImportCheck {
    private static final String OLD="a".repeat(32),NEW="b".repeat(32);
    private static <T> T unused(Class<T> type) {
        return type.cast(Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},(proxy,method,args)-> {
            throw new AssertionError("Unexpected native call: "+method.getName());
        }));
    }
    private static class Qc extends QcResultImporter {
        int calls;
        Qc(PlatformTransactionManager tx) {super(null,null,null,null,tx);}
        @Override void apply(String owner,String sample,String delivery,Path dir,List<Map<String,Object>> files,Map<String,Long> counts) {
            calls++;
            if(files.size()!=1||!NEW.equals(((Map<?,?>)files.get(0).get("pipeline_result")).get("job_id")))throw new AssertionError("QC jobs mixed");
            if(counts.get("InputReads")!=10)throw new AssertionError("QC counts lost");
        }
    }
    private static Map<String,Object> file(String id,String job,int time,String key) {
        return Map.of("id",id,"name","renamed.tsv","pipeline_result",Map.of("job_id",job,"completed_at",time,"output_key",key));
    }
    private static Map<String,Object> receipt() {
        return new HashMap<>(Map.of("files",List.of(file("old",OLD,1,"ReadQc.qc_summary"),file("new",NEW,2,"ReadQc.qc_summary"))));
    }
    private static String state(Map<String,Object> receipt,String job) {
        return ((List<Map<String,Object>>)receipt.get("native_imports")).stream().filter(r->job.equals(r.get("job_id"))).map(r->String.valueOf(r.get("state"))).findFirst().orElseThrow();
    }
    public static void main(String[] args) throws Exception {
        var registry=new ResultImporterRegistry(unused(IAssemblyResultService.class),unused(IMetaxResultService.class),
            unused(IFuncReadsResultService.class),unused(IFuncAssemblyResultService.class),unused(IAnnotatorResultService.class),
            unused(IMetadataProcessService.class),unused(IStrainProfileService.class),unused(IStrainCoptrService.class),unused(IGenomeTracingService.class),unused(IStrainCoptrResultService.class));
        if(registry.capabilities().size()!=17)throw new AssertionError("Format registrations lost");
        var tx=unused(PlatformTransactionManager.class);var qc=new Qc(tx);
        var imports=new ResultImportService(null,null,tx,registry,qc);
        Path dir=Files.createTempDirectory("result-import-check-");
        try {
            for(String id:List.of("old","new"))Files.writeString(dir.resolve(id),"InputReads\t10\nReadsAfterQC\t9\nReadsAfterHostRemoval\t8\n");
            var current=receipt();
            imports.importReceipt("owner","sample","meta","delivery",dir,current,List.of());
            if(qc.calls!=1||!state(current,NEW).equals("imported")||!state(current,OLD).equals("not_imported"))throw new AssertionError("QC selection changed");
            imports.importResults("owner","sample","meta","delivery",dir,current);
            if(qc.calls!=1||!state(current,NEW).equals("imported"))throw new AssertionError("Retry reapplied QC");
            var stale=receipt();
            imports.importReceipt("owner","sample","meta","delivery",dir,stale,List.of(Map.of("qc",Map.of("InputReads",12),"qc_completed_at",3)));
            if(qc.calls!=1||!state(stale,NEW).equals("not_imported"))throw new AssertionError("Newer QC overwritten");
            var incompatible=receipt();
            imports.importReceipt("owner","sample","genomic","delivery",dir,incompatible,List.of());
            if(qc.calls!=1||!state(incompatible,NEW).equals("not_imported"))throw new AssertionError("Sample type check lost");
            var unknown=new HashMap<String,Object>(Map.of("files",List.of(file("unknown",NEW,2,"Custom.report"))));
            imports.importReceipt("owner","sample","meta","delivery",dir,unknown,List.of());
            if(!state(unknown,NEW).equals("unsupported")||!Boolean.FALSE.equals(unknown.get("native_import_failed")))throw new AssertionError("File-only fallback lost");
            var outcome=((List<Map<String,Object>>)unknown.get("native_imports")).get(0);
            if(!"imported".equals(((Map<?,?>)outcome.get("generic_import")).get("state")))throw new AssertionError("Generic delivery outcome missing");
            var array=imports.apply("owner","sample","genomic","delivery",dir,List.of(file("a",NEW,2,"Custom.array"),file("b",NEW,2,"Custom.array"))).get(0);
            if(!"Custom".equals(array.get("format"))||String.valueOf(array.get("message")).contains("Duplicate"))throw new AssertionError("Legitimate array rejected as duplicate roles");
            var ambiguous=imports.apply("owner","sample","meta","delivery",dir,List.of(file("a",NEW,2,"metax.profile"),file("b",NEW,2,"metax.profile"))).get(0);
            if(!"incomplete".equals(ambiguous.get("state")))throw new AssertionError("Ambiguous native scalar accepted");
            String emptyId="e".repeat(64);Files.writeString(dir.resolve(emptyId),"log2(PTR):genome_id/sample_id,reads\n");
            var empty=imports.apply("owner","sample","meta","delivery",dir,List.of(file(emptyId,NEW,2,"StrainCoPTR.log2ptr_csv"))).get(0);
            if(!"empty".equals(empty.get("state")))throw new AssertionError("Header-only growth must not run the native parser or overwrite records");
            Files.writeString(dir.resolve(emptyId),"id,reads\nexample,1\n");
            if(!ResultImportService.hasDataRow(dir.resolve(emptyId)))throw new AssertionError("Nonempty CSV treated as empty");
            Files.delete(dir.resolve(emptyId));
            System.out.println("PASS importer registry, job scoping, retry, newer-result preservation, sample types and file-only fallback");
        } finally {
            Files.deleteIfExists(dir.resolve("old"));Files.deleteIfExists(dir.resolve("new"));Files.deleteIfExists(dir);
        }
    }
}
