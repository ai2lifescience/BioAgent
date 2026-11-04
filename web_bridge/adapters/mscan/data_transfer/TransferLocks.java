package com.mscan.web.controller.common;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.stereotype.Component;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.locks.ReentrantLock;

/** Shared process-local locks for destination creation, sample writes and receipt replay. */
@Component
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class TransferLocks {
    private record Key(String kind,String owner,String id) {}
    private static class Entry {
        final ReentrantLock lock=new ReentrantLock(true);
        int users;
    }
    private final Map<Key,Entry> entries=new HashMap<>();

    public Guard owner(String owner) throws InterruptedException {return acquire(new Key("owner",owner,""));}
    public Guard sample(String owner,String sample) throws InterruptedException {return acquire(new Key("sample",owner,sample));}
    public Guard receipt(String receipt) throws InterruptedException {return acquire(new Key("receipt","",receipt));}
    private Guard acquire(Key key) throws InterruptedException {
        Entry entry;
        synchronized(entries) {entry=entries.computeIfAbsent(key,k->new Entry());entry.users++;}
        try {entry.lock.lockInterruptibly();return new Guard(key,entry);}
        catch(InterruptedException error) {release(key,entry);throw error;}
    }
    private void release(Key key,Entry entry) {
        synchronized(entries) {if(--entry.users==0)entries.remove(key,entry);}
    }
    public final class Guard implements AutoCloseable {
        private final Key key;
        private final Entry entry;
        private boolean closed;
        private Guard(Key key,Entry entry) {this.key=key;this.entry=entry;}
        @Override public void close() {
            if(closed)return;
            closed=true;entry.lock.unlock();release(key,entry);
        }
    }
}
