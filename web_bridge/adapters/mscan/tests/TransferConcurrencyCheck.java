package com.mscan.web.controller.common;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.transaction.PlatformTransactionManager;
import java.lang.reflect.Proxy;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.AtomicInteger;

/** Exercise the production dispatcher with blocked work, failures and real keyed locks. */
public class TransferConcurrencyCheck {
    static void require(boolean value,String message) {if(!value)throw new AssertionError(message);}
    static void await(CountDownLatch latch) throws Exception {require(latch.await(5,TimeUnit.SECONDS),"Timed out waiting for work");}
    static class Bridge extends AssistantController {
        final BlockingQueue<Map<String,Object>> acknowledgements=new LinkedBlockingQueue<>();
        Bridge(){super(new ObjectMapper(),null,null,null,null);}
        @Override Map<String,Object> callAs(String owner,String path,Map<String,Object> body) {
            if(path.equals("command-ack"))acknowledgements.add(body);
            return Map.of();
        }
    }
    static class Service extends AssistantTransferService {
        final Queue<Map<String,Object>> pending=new ConcurrentLinkedQueue<>();
        final Map<String,CountDownLatch> started=new ConcurrentHashMap<>(),release=new ConcurrentHashMap<>();
        final AtomicInteger leases=new AtomicInteger(),running=new AtomicInteger(),maximum=new AtomicInteger();
        final Set<String> failures=ConcurrentHashMap.newKeySet();
        Service(Bridge bridge,int workers) {
            super(bridge,null,null,null,null,null,null,null,
                (PlatformTransactionManager)Proxy.newProxyInstance(PlatformTransactionManager.class.getClassLoader(),new Class<?>[]{PlatformTransactionManager.class},(p,m,a)->{throw new AssertionError("Unexpected DB call");}),workers);
        }
        void add(String id,boolean block) {
            started.put(id,new CountDownLatch(1));release.put(id,new CountDownLatch(block?1:0));
            pending.add(Map.of("id",id,"lease","lease-"+id,"operation","search"));
        }
        @Override Map<String,Object> nextCommand(){leases.incrementAndGet();return pending.poll();}
        @Override Map<String,Object> execute(Map<String,Object> command) throws Exception {
            String id=(String)command.get("id");int count=running.incrementAndGet();maximum.accumulateAndGet(count,Math::max);
            try {started.get(id).countDown();await(release.get(id));if(failures.contains(id))throw new IllegalStateException("fixture failure");return Map.of("id",id);}
            finally {running.decrementAndGet();}
        }
    }
    public static void main(String[] args) throws Exception {
        var bridge=new Bridge();var service=new Service(bridge,2);
        try {
            service.add("slow",true);service.add("fast",true);service.add("later",false);
            service.poll();await(service.started.get("slow"));await(service.started.get("fast"));
            require(service.maximum.get()==2,"Transfers did not run concurrently");
            int leased=service.leases.get();service.poll();require(service.leases.get()==leased,"Leased without free capacity");
            service.release.get("fast").countDown();
            var ack=bridge.acknowledgements.poll(5,TimeUnit.SECONDS);require(ack!=null&&ack.get("id").equals("fast"),"Fast user blocked behind slow transfer");
            long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
            while(service.started.get("later").getCount()!=0&&System.nanoTime()<deadline){service.poll();Thread.sleep(10);}
            await(service.started.get("later"));
            require(service.maximum.get()==2,"Concurrency bound exceeded");
            service.release.get("slow").countDown();
            service.add("failure",false);service.failures.add("failure");
            deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(5);
            while(service.started.get("failure").getCount()!=0&&System.nanoTime()<deadline){service.poll();Thread.sleep(10);}
            await(service.started.get("failure"));
            boolean failed=false;
            for(int i=0;i<3;i++){ack=bridge.acknowledgements.poll(5,TimeUnit.SECONDS);require(ack!=null,"Missing acknowledgement");if(ack.get("id").equals("failure"))failed=Boolean.FALSE.equals(ack.get("ok"));}
            require(failed,"Failed command was not acknowledged");
            service.close();leased=service.leases.get();service.poll();require(service.leases.get()==leased,"Closed worker leased commands");
        } finally {service.release.values().forEach(CountDownLatch::countDown);service.close();}
        var locks=new TransferLocks();var pool=Executors.newFixedThreadPool(2);
        try {
            var waiting=new CountDownLatch(1);var acquired=new CountDownLatch(1);
            Future<?> same;
            try(var sample=locks.sample("alice","one")) {
                // Nested receiver acquisition must not deadlock the push worker.
                try(var nested=locks.sample("alice","one")) {}
                same=pool.submit(()->{waiting.countDown();try(var guard=locks.sample("alice","one")){acquired.countDown();}catch(Exception e){throw new RuntimeException(e);}});
                await(waiting);
                var other=pool.submit(()->{try(var guard=locks.sample("bob","two")){return true;}});
                require(other.get(5,TimeUnit.SECONDS),"Unrelated sample blocked");
                require(acquired.getCount()==1,"Same sample writes overlapped");
            }
            same.get(5,TimeUnit.SECONDS);await(acquired);
            try {try(var guard=locks.owner("alice")){throw new IllegalStateException("fixture");}}catch(IllegalStateException expected){}
            try(var guard=locks.owner("alice")){}
            var field=TransferLocks.class.getDeclaredField("entries");field.setAccessible(true);
            require(((Map<?,?>)field.get(locks)).isEmpty(),"Unused keyed locks leaked");
        } finally {pool.shutdownNow();}
        System.out.println("PASS bounded concurrent transfers, no excess leasing, independent-user progress, failure acknowledgement, shutdown and sample-lock cleanup");
    }
}
