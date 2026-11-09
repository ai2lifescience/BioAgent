package com.mscan.web.controller.common;

import java.nio.file.*;
import java.util.*;

public class ResultArtifactCheck {
    private static void require(boolean ok,String message){if(!ok)throw new AssertionError(message);}
    public static void main(String[] args)throws Exception {
        Path file=Files.createTempFile("result-artifact-",".dat");
        try {
            Files.writeString(file,"item\tvalue\nexample\t1\n");
            var table=ResultArtifactInspector.inspect(file);
            require(table.get("kind").equals("table"),"Renamed TSV not discovered");
            require(table.get("columns").equals(List.of("item","value")),"Columns lost");
            Files.writeString(file,"\ufeffitem,value\r\n\"two, lines\nwith \"\"quotes\"\"\",42\r\n");
            table=ResultArtifactInspector.inspect(file);
            require(table.get("preview_rows").equals(List.of(List.of("two, lines\nwith \"quotes\"","42"))),"Quoted CSV parsed incorrectly");
            Files.writeString(file,"item,value\na,1,extra\n");
            require(!ResultArtifactInspector.inspect(file).get("kind").equals("table"),"Malformed table accepted");
            Files.writeString(file,"item,item\na,1\n");
            require(!ResultArtifactInspector.inspect(file).get("kind").equals("table"),"Ambiguous columns accepted");
            Files.writeString(file,"[{\"item\":\"example\",\"value\":1}]");
            require(ResultArtifactInspector.inspect(file).get("fields").equals(List.of("item","value")),"JSON fields missing");
            Files.write(file,new byte[]{0,1,2,(byte)255});
            require(ResultArtifactInspector.inspect(file).get("kind").equals("file"),"Binary not preserved");
            String large="item\tvalue\n"+"example\t1\n".repeat(100000);
            Files.writeString(file,large);long size=Files.size(file);
            table=ResultArtifactInspector.inspect(file);
            require(((List<?>)table.get("preview_rows")).size()==3,"Unbounded preview");
            require(Files.size(file)==size,"Preview modified artifact");
            Files.writeString(file,"item,value\n"+"x".repeat(2000)+",1\n");
            require(new com.fasterxml.jackson.databind.ObjectMapper().writeValueAsBytes(ResultArtifactInspector.inspect(file)).length<=1536,"Discovery metadata too large");
            var error=new IllegalStateException("closed pending result",new java.sql.SQLException("Failed to parse port from http_proxy 'http://secret@proxy:123/'"));
            var diagnostic=ImportFailure.describe(error);
            require(diagnostic.get("error_code").equals("storage_proxy_configuration"),"Root failure hidden");
            require(!diagnostic.toString().contains("secret@"),"Credential leaked");
            System.out.println("PASS generic TSV/CSV/JSON/binary discovery, malformed headers, bounded previews and credential-free root-cause diagnostics");
        } finally {Files.deleteIfExists(file);}
    }
}
