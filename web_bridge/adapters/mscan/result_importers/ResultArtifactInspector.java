package com.mscan.web.controller.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.*;

/** Pipeline-independent discovery metadata. Preview limits never limit file delivery. */
public final class ResultArtifactInspector {
    private static final int PREFIX_BYTES=65536;
    private ResultArtifactInspector() {}
    public static Map<String,Object> inspect(Path path) {
        var result=new LinkedHashMap<String,Object>(read(path));
        try {
            if(new ObjectMapper().writeValueAsBytes(result).length>1536) {
                result.remove("preview_rows");result.remove("preview");
                for(String key:List.of("columns","fields"))if(result.get(key) instanceof List<?> values)
                    result.put(key,values.stream().limit(8).map(v->clip(String.valueOf(v),48)).toList());
                result.put("metadata_truncated",true);
            }
            if(new ObjectMapper().writeValueAsBytes(result).length>1536)
                return Map.of("kind",result.get("kind"),"preview_available",false,"metadata_truncated",true);
        } catch(java.io.IOException ignored) {return Map.of("kind","file","preview_available",false);}
        return result;
    }
    private static Map<String,Object> read(Path path) {
        try(var stream=Files.newInputStream(path)) {
            byte[] bytes=stream.readNBytes(PREFIX_BYTES+1);
            boolean truncated=bytes.length>PREFIX_BYTES;
            // UTF-8 may end halfway through a character when reading a bounded prefix.
            int length=Math.min(bytes.length,PREFIX_BYTES);
            String text=null;
            for(int trim=0;trim<=(truncated?3:0);trim++)try {
                text=StandardCharsets.UTF_8.newDecoder().decode(ByteBuffer.wrap(bytes,0,length-trim)).toString();break;
            } catch(java.nio.charset.CharacterCodingException ignored) {}
            if(text==null||text.indexOf('\0')>=0)return Map.of("kind","file","preview_available",false);
            if(text.startsWith("\ufeff"))text=text.substring(1);
            if(!truncated&&(text.stripLeading().startsWith("{")||text.stripLeading().startsWith("["))) {
                try {
                    var json=new ObjectMapper().readTree(text);
                    var fields=new ArrayList<String>();
                    var object=json.isObject()?json:json.isArray()&&!json.isEmpty()?json.get(0):null;
                    if(object!=null&&object.isObject())object.fieldNames().forEachRemaining(k->{if(fields.size()<32)fields.add(clip(k,128));});
                    return Map.of("kind","json","fields",fields,"shape",json.isArray()?"array":"object","preview_available",true);
                } catch(java.io.IOException ignored) {}
            }
            for(char delimiter:new char[]{'\t',','}) {
                var rows=records(text,delimiter,!truncated);
                if(rows.size()<2)continue;
                var header=rows.get(0);
                if(header.size()<2||header.size()>32||new HashSet<>(header).size()!=header.size()
                    ||header.stream().anyMatch(s->s.isBlank()||s.length()>128)
                    ||rows.stream().anyMatch(r->r.size()!=header.size()))continue;
                var preview=rows.subList(1,rows.size()).stream().map(r->r.stream().map(s->clip(s,256)).toList()).toList();
                return Map.of("kind","table","delimiter",delimiter=='\t'?"tab":"comma","columns",header,
                    "preview_rows",preview,"preview_only",true,"preview_available",true);
            }
            return Map.of("kind","text","preview",clip(text,1024),"preview_only",true,"preview_available",true);
        } catch(java.io.IOException|RuntimeException error) {
            // Optional discovery cannot prevent delivery or turn an unreadable preview into native success.
            return Map.of("kind","file","preview_available",false);
        }
    }
    private static String clip(String value,int length) {return value.length()<=length?value:value.substring(0,length)+"…";}
    /** Read a header and up to three complete records, including quoted CSV fields/newlines. */
    private static List<List<String>> records(String text,char delimiter,boolean complete) {
        var rows=new ArrayList<List<String>>();var row=new ArrayList<String>();var cell=new StringBuilder();
        boolean quoted=false,closed=false;
        for(int i=0;i<text.length();i++) {
            char c=text.charAt(i);
            if(quoted) {
                if(c=='"') {
                    if(i+1<text.length()&&text.charAt(i+1)=='"'){cell.append('"');i++;}
                    else {quoted=false;closed=true;}
                } else cell.append(c);
            } else if(c=='"') {
                if(!cell.isEmpty()||closed)return List.of();quoted=true;
            } else if(c==delimiter||c=='\n'||c=='\r') {
                row.add(cell.toString());cell.setLength(0);closed=false;
                if(row.size()>32)return List.of();
                if(c!=delimiter) {
                    rows.add(new ArrayList<>(row));row.clear();
                    if(rows.size()==4)return rows;
                    if(c=='\r'&&i+1<text.length()&&text.charAt(i+1)=='\n')i++;
                }
            } else {if(closed)return List.of();cell.append(c);}
        }
        if(complete&&!quoted&&(!row.isEmpty()||!cell.isEmpty()||closed)){row.add(cell.toString());rows.add(row);}
        return rows;
    }
}
