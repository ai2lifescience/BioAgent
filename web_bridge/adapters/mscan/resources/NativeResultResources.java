package com.mscan.web.controller.common;

import com.baomidou.mybatisplus.core.conditions.query.QueryWrapper;
import com.baomidou.mybatisplus.extension.service.IService;
import com.mscan.database.service.*;
import com.mscan.database.mapper.IMetadataMapper;
import com.mscan.database.mapper.IFastSampleMapper;
import org.springframework.beans.BeanWrapperImpl;
import org.springframework.stereotype.Service;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import java.net.URI;
import java.util.*;

/** Discover file-valued native results; every resolution rechecks sample ownership. */
@Service
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class NativeResultResources {
    public record File(Map<String,Object> descriptor,String bucket,String key,byte[] data) {}
    private final com.fasterxml.jackson.databind.ObjectMapper json;
    private final Map<String,IService> providers;
    private final IMetadataMapper metadata;
    private final IFastSampleMapper fasta;
    public NativeResultResources(IMetadataMapper metadata,IFastSampleMapper fasta,IQcResultRecordService qc,
            IAssemblyResultService assembly,IFuncReadsResultService reads,IFuncAssemblyResultService genomes,
            IMetaxResultService metax,IAnnotatorResultService annotations,IBacResultService bac,ISnpResultService snp,
            IStrainCoptrResultService growth,IStrainProfileService profiles,IMashSummaryService mash,
            IDetectionResultKmerService kmer,com.fasterxml.jackson.databind.ObjectMapper json) {
        this.metadata=metadata;this.fasta=fasta;this.json=json;
        this.providers=Map.ofEntries(Map.entry("qc",qc),Map.entry("assembly",assembly),Map.entry("func_reads",reads),Map.entry("func_assembly",genomes),
            Map.entry("metax",metax),Map.entry("annotation",annotations),Map.entry("bac",bac),Map.entry("snp",snp),
            Map.entry("growth",growth),Map.entry("strain_profile",profiles),Map.entry("mash",mash),Map.entry("kmer",kmer));
    }
    private void owned(String owner,String sample) {
        var reads=metadata.selectById(sample);var genome=fasta.selectById(sample);
        if((reads==null||!owner.equals(reads.getCreateBy()))&&(genome==null||!owner.equals(genome.getCreateBy())))throw new IllegalArgumentException("Sample not found.");
    }
    public List<Map<String,Object>> catalog(String owner,String sample) {
        owned(owner,sample);return catalogRows(Set.of(sample));
    }
    public List<Map<String,Object>> catalogMany(String owner,Set<String> requested) {
        if(requested.isEmpty())return List.of();
        Set<String> owned=new HashSet<>();
        for(var row:metadata.selectList(new QueryWrapper<com.mscan.database.domain.entity.Metadata>().eq("create_by",owner).in("id",requested)))owned.add(row.getId());
        for(var row:fasta.selectList(new QueryWrapper<com.mscan.database.domain.entity.FastaSample>().eq("create_by",owner).in("id",requested)))owned.add(row.getId());
        return catalogRows(owned);
    }
    private List<Map<String,Object>> catalogRows(Set<String> samples) {
        if(samples.isEmpty())return List.of();
        List<Map<String,Object>> result=new ArrayList<>();
        for(var provider:providers.entrySet())for(Object row:provider.getValue().list(new QueryWrapper<>().in("sample_id",samples))) {
            var bean=new BeanWrapperImpl(row);String id=String.valueOf(bean.getPropertyValue("id")),sample=String.valueOf(bean.getPropertyValue("sampleId"));
            if(!samples.contains(sample))continue;
            result.add(record(sample,provider.getKey(),id,row).descriptor());
            for(var property:bean.getPropertyDescriptors())if(property.getPropertyType()==String.class) {
                Object value=bean.getPropertyValue(property.getName());
                if(value instanceof String path && path.startsWith("s3://")) {
                    String resource="native:"+sample+":"+provider.getKey()+":"+id+":"+property.getName();
                    result.add(describe(sample,provider.getKey(),resource,path).descriptor());
                }
            }
        }
        return result;
    }
    private File record(String sample,String program,String id,Object row) {
        try {
            byte[] data=json.writeValueAsBytes(row);
            return new File(Map.of("resource_id","native:"+sample+":"+program+":"+id+":record", "sample_id",sample,
                "program",program,"name",program+"-"+id+".json","kind","native_analysis_record","importable",true,"size",data.length),null,null,data);
        } catch(java.io.IOException error) {throw new IllegalStateException("Native result export failed.",error);}
    }
    private File describe(String sample,String program,String resource,String path) {
        URI uri=URI.create(path);String key=uri.getPath().replaceFirst("^/","");
        if(!"s3".equals(uri.getScheme())||uri.getHost()==null||key.isBlank()||uri.getQuery()!=null||uri.getFragment()!=null)throw new IllegalArgumentException("Invalid native object path.");
        String name=key.substring(key.lastIndexOf('/')+1);
        return new File(Map.of("resource_id",resource,"sample_id",sample,"program",program,"name",name,"kind","native_analysis_output","importable",true),uri.getHost(),key,null);
    }
    public File resolve(String owner,String resource) {
        String[] parts=resource.split(":",-1);
        if(parts.length!=5||!parts[0].equals("native")||!providers.containsKey(parts[2])||!parts[4].matches("[A-Za-z][A-Za-z0-9]*"))throw new IllegalArgumentException("Native result not found.");
        owned(owner,parts[1]);Object row=providers.get(parts[2]).getById(parts[3]);
        if(row==null)throw new IllegalArgumentException("Native result not found.");
        var bean=new BeanWrapperImpl(row);
        if(!parts[1].equals(bean.getPropertyValue("sampleId")))throw new IllegalArgumentException("Native result not found.");
        if(parts[4].equals("record"))return record(parts[1],parts[2],parts[3],row);
        if(!bean.isReadableProperty(parts[4]))throw new IllegalArgumentException("Native result not found.");
        Object value=bean.getPropertyValue(parts[4]);
        if(!(value instanceof String path)||!path.startsWith("s3://"))throw new IllegalArgumentException("Native file not found.");
        return describe(parts[1],parts[2],resource,path);
    }
}
