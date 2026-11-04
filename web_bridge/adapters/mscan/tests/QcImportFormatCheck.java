package com.mscan.web.controller.common;
import java.nio.file.*;
import java.util.Map;
public class QcImportFormatCheck {
    public static void main(String[]args)throws Exception {
        Path file=Files.createTempFile("qc-format-check-",".tsv");
        try {
            Files.writeString(file,"InputReads\t10\nReadsAfterQC\t9\nReadsAfterHostRemoval\t8\n");
            if(QcResultImporter.readCounts(file).get("ReadsAfterQC")!=9)throw new AssertionError();
            Files.writeString(file,"MetricName\tMetricValue\nInputReads\t4168\nReadsAfterQC\t4168\nReadsAfterHostRemoval\t4149\n");
            if(QcResultImporter.readCounts(file).get("ReadsAfterHostRemoval")!=4149)throw new AssertionError("Legacy header or equal counts rejected");
            String header="sample\tlayout\traw_reads\tquality_dropped_reads\tunivec_core_hit_reads\treads_before_host\thost_reads\tfinal_clean_reads\n";
            String row="fixture\tSE\t10\t1\t0\t9\t1\t8\n";
            Files.writeString(file,header+row);
            var value=QcResultImporter.readCounts(file);
            if(value.get("HostReads")!=1||value.get("ReadsAfterQC")!=9||value.get("ReadsAfterHostRemoval")!=8)throw new AssertionError();
            Files.writeString(file,header+row+row);
            try {QcResultImporter.readCounts(file);throw new AssertionError("Mixed samples accepted");}catch(java.io.IOException expected){}
            for(String invalid:new String[]{"InputReads\t10\nReadsAfterQC\t11\nReadsAfterHostRemoval\t8\n", "InputReads\t10\n", "InputReads\t-1\nReadsAfterQC\t0\nReadsAfterHostRemoval\t0\n"}) {
                Files.writeString(file,invalid);
                try {QcResultImporter.readCounts(file);throw new AssertionError("Invalid counts accepted");}catch(java.io.IOException expected){}
            }
            if(!QcResultImporter.role(Map.of("name","renamed.dat","pipeline_result",Map.of("output_key","ReadQc.clean_r1"))).equals("r1"))throw new AssertionError();
            System.out.println("PASS both QC formats, legacy header, renamed roles, mixed samples and incomplete, negative or inconsistent counts");
        } finally {Files.deleteIfExists(file);}
    }
}
