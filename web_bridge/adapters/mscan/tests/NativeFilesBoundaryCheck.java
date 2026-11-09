import com.mscan.web.controller.common.NativeResultResources;
import com.mscan.database.domain.entity.*;
import com.mscan.database.mapper.*;
import com.mscan.database.service.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.lang.reflect.Proxy;
import java.util.List;

/** Standalone boundary check; run with the built MSCAN modules and dependency jars. */
public class NativeFilesBoundaryCheck {
    @SuppressWarnings("unchecked")
    static <T>T stub(Class<T> type,java.util.function.BiFunction<String,Object[],Object> action) {
        return (T)Proxy.newProxyInstance(type.getClassLoader(),new Class[]{type},(p,m,a)->action.apply(m.getName(),a));
    }
    static <T>T empty(Class<T> type) {return stub(type,(m,a)->m.equals("list")||m.equals("selectList")?List.of():null);}
    static void denied(Runnable action) {try {action.run();throw new AssertionError("Access was allowed");}catch(IllegalArgumentException expected){}}
    public static void main(String[]args) throws Exception {
        var sample=new Metadata();sample.setId("sample-a");sample.setCreateBy("alice");
        var other=new Metadata();other.setId("sample-b");other.setCreateBy("alice");
        var rows=stub(IMetadataMapper.class,(m,a)-> {
            if(m.equals("selectById"))return "sample-a".equals(a[0])?sample:"sample-b".equals(a[0])?other:null;
            if(m.equals("selectList")) {
                var query=(com.baomidou.mybatisplus.core.conditions.query.QueryWrapper<?>)a[0];query.getSqlSegment();
                return query.getParamNameValuePairs().containsValue("alice")?List.of(sample):List.of();
            }
            return null;
        });
        var record=new AssemblyResult();record.setId("row-a");record.setSampleId("sample-a");record.setFinalContigsRenamed("s3://test-results/fixture.fa");record.setTaskId("private-task");
        var assembly=stub(IAssemblyResultService.class,(m,a)->m.equals("getById")?record:m.equals("list")?List.of(record):null);
        var service=new NativeResultResources(rows,empty(IFastSampleMapper.class),empty(IQcResultRecordService.class),assembly,
            empty(IFuncReadsResultService.class),empty(IFuncAssemblyResultService.class),empty(IMetaxResultService.class),
            empty(IAnnotatorResultService.class),empty(IBacResultService.class),empty(ISnpResultService.class),
            empty(IStrainCoptrResultService.class),empty(IStrainProfileService.class),empty(IMashSummaryService.class),empty(IDetectionResultKmerService.class),new ObjectMapper());
        String file="native:sample-a:assembly:row-a:finalContigsRenamed";
        var allowed=service.resolve("alice",file);
        if(!allowed.bucket().equals("test-results")||!allowed.key().equals("fixture.fa"))throw new AssertionError("Wrong object");
        denied(()->service.resolve("bob",file));
        denied(()->service.resolve("alice",file.replace("sample-a","sample-b")));
        denied(()->service.resolve("alice",file.replace("finalContigsRenamed","class.classLoader")));
        denied(()->service.resolve("alice",file.replace("finalContigsRenamed","taskId")));
        var exported=service.resolve("alice",file.replace("finalContigsRenamed","record"));
        if(!new ObjectMapper().readTree(exported.data()).get("sampleId").asText().equals("sample-a"))throw new AssertionError("Wrong record");
        denied(()->service.resolve("bob",file.replace("finalContigsRenamed","record")));
        denied(()->service.catalog("bob","sample-a"));
        if(!service.catalogMany("bob",java.util.Set.of("sample-a")).isEmpty())throw new AssertionError("Batched catalog leaked data");
        if(service.catalogMany("alice",java.util.Set.of("sample-a")).isEmpty())throw new AssertionError("Owned batch unavailable");
        System.out.println("PASS native file and JSON exports enforce owner, sample, row and field boundaries");
    }
}
