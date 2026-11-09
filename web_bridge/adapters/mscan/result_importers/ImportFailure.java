package com.mscan.web.controller.common;

import java.util.*;

/** Stable, credential-free failure categories; JDBC messages may contain secrets or SQL. */
public final class ImportFailure {
    private ImportFailure() {}
    public static Map<String,Object> describe(Throwable failure) {
        Set<Throwable> seen=Collections.newSetFromMap(new IdentityHashMap<>());
        StringBuilder messages=new StringBuilder();
        for(Throwable error=failure;error!=null&&seen.add(error);error=error.getCause())
            messages.append(' ').append(String.valueOf(error.getMessage()).toLowerCase(Locale.ROOT));
        String text=messages.toString(),code="native_import_failed",message="Native import failed. Delivered files remain available; check the backend configuration and result contract.";
        if(text.contains("http_proxy")||text.contains("https_proxy")) {
            code="storage_proxy_configuration";
            message="MSCAN's table reader rejected its proxy configuration. Remove a trailing slash from HTTP(S) proxy URLs, restart the backend and retry this transfer.";
        } else if(text.contains("httpfs")||text.contains("extension")) {
            code="table_reader_dependency";message="The table reader's storage extension is unavailable. Configure DuckDB httpfs on the backend and retry.";
        } else if(text.contains("binder error")||text.contains("column")||text.contains("csv error")) {
            code="result_schema_mismatch";message="The result table does not satisfy the native parser's schema. Original files remain available.";
        } else if(text.contains("connection refused")||text.contains("timed out")||text.contains("http error")) {
            code="result_storage_unavailable";message="The table reader could not access result storage. Check backend connectivity and storage credentials, then retry.";
        }
        return Map.of("error_code",code,"message",message);
    }
}
