package com.mscan.web.controller.common;

import com.mscan.database.domain.entity.SampleTaskInfo;
import com.mscan.database.service.*;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import java.util.*;
import java.util.function.Consumer;

/** Maps result formats to MSCAN's native parsers and advertises their contracts. */
@Component
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class ResultImporterRegistry {
    public record Rule(String program,Set<String> types,Set<String> required,Consumer<SampleTaskInfo> importer) {}
    private final Map<String,Rule> rules=new LinkedHashMap<>();
    public ResultImporterRegistry(IAssemblyResultService assembly,IMetaxResultService metax,
            IFuncReadsResultService reads,IFuncAssemblyResultService genomes,IAnnotatorResultService annotations,
            IMetadataProcessService processes,IStrainProfileService profiles,IStrainCoptrService growth) {
        Set<String> meta=Set.of("meta","shortReads"),genome=Set.of("genomic","synthetic"),all=Set.of("meta","shortReads","genomic","synthetic");
        add("AssemblyId","assembly",meta,Set.of("species_report_tsv","contig_report_tsv","final_contigs_renamed"),assembly::handleAssemblySucceeded);
        add("metax","metax",meta,Set.of("profile"),metax::handleMetaxSucceeded);
        add("FuncReads","funcflow",meta,Set.of("gene_annotations_tsv"),reads::handleSucceeded);
        add("FuncAssembly","funcflow",genome,Set.of("gene_annotations_tsv"),genomes::handleSucceeded);
        add("StrainMeta","strain_meta",meta,Set.of("profile"),profiles::handleStrainMetaSucceeded);
        add("StrainCoPTR","growth",meta,Set.of("log2ptr_csv"),growth::handleGrowthSucceeded);
        add("BacDef","bacdef",all,Set.of("defense_systems","defense_genes","defense_hmmer_hits"),processes::handleBacDefSucceeded);
        add("BacSec","bacsec",all,Set.of("secretion_systems","secretion_genes"),processes::handleBacSecSucceeded);
        add("BacBGC","bacbgc",all,Set.of("bgc_clusters","bgc_genes","bgc_features"),processes::handleBacBgcSucceeded);
        for(String prefix:List.of("PhiAnnotatorGenome","PhiAnnotatorMetagenome","TcdbAnnotatorGenome","TcdbAnnotatorMetagenome")) {
            String program=prefix.startsWith("Phi")?"phi":"tcdb";
            add(prefix,program,prefix.endsWith("Genome")?genome:meta,Set.of("summary","hits"),t->annotations.handleSucceeded(program,t));
        }
    }
    private void add(String format,String program,Set<String> types,Set<String> required,Consumer<SampleTaskInfo> handler) {
        rules.put(format,new Rule(program,types,required,handler));
    }
    public List<Map<String,Object>> capabilities() {
        var result=new ArrayList<>(rules.entrySet().stream().map(e->Map.<String,Object>of("format",e.getKey(),"program",e.getValue().program(),
            "sample_types",e.getValue().types(),"required_outputs",e.getValue().required())).toList());
        result.add(Map.of("format","MetagenomicQc","program","qc","sample_types",List.of("meta","shortReads"),"required_outputs",List.of("qc_counts")));
        result.add(Map.of("format","ReadQc","program","qc","sample_types",List.of("meta","shortReads"),"required_outputs",List.of("qc_summary")));
        return result;
    }
    public Rule find(String format) {
        return rules.get(format);
    }
}
