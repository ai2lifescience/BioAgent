package com.mscan.web.controller.common;

import com.google.gson.JsonObject;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;

/** Supply already-owned imported files to existing native parsers, only on this thread. */
@Aspect
@Component
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class NativeImportContext {
    private record Import(String task,JsonObject metadata) {}
    private static final ThreadLocal<Import> CURRENT=new ThreadLocal<>();
    public static void run(String task,JsonObject metadata,Runnable action) {
        if(CURRENT.get()!=null)throw new IllegalStateException("Nested result import.");
        CURRENT.set(new Import(task,metadata.deepCopy()));
        try {action.run();} finally {CURRENT.remove();}
    }
    @Around("execution(* com.mscan.database.service.ICromwellWorkflowService.*(..))")
    public Object workflow(ProceedingJoinPoint call) throws Throwable {
        Import value=CURRENT.get();
        if(value==null)return call.proceed();
        if(call.getSignature().getName().equals("getWorkflowMetadata") && value.task().equals(call.getArgs()[0]))return value.metadata().deepCopy();
        throw new IllegalStateException("Result import cannot submit, poll or mutate remote workflows.");
    }
}
