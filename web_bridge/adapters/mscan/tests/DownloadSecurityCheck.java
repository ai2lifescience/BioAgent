import com.mscan.web.controller.common.WebsiteDownloadSecurity;
import com.mscan.web.controller.common.AssistantController;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.http.*;
import org.springframework.context.annotation.*;
import org.springframework.core.annotation.Order;
import org.springframework.core.env.MapPropertySource;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.*;
import java.lang.reflect.Proxy;
import java.util.*;
import java.io.*;

/** Build real Spring filter chains and verify that only ticket GETs bypass host authentication. */
public class DownloadSecurityCheck {
    @Configuration
    @EnableWebSecurity
    static class HostSecurity {
        @Bean @Order(0)
        SecurityFilterChain hostChain(HttpSecurity http) throws Exception {
            http.authorizeHttpRequests(auth->auth.anyRequest().authenticated());return http.build();
        }
        @Bean CorsConfigurationSource corsConfigurationSource() {return new UrlBasedCorsConfigurationSource();}
    }
    static HttpServletRequest request(String method,String path) {
        return (HttpServletRequest)Proxy.newProxyInstance(HttpServletRequest.class.getClassLoader(),new Class<?>[]{HttpServletRequest.class},(p,m,a)->switch(m.getName()) {
            case "getMethod" -> method;
            case "getServletPath", "getRequestURI" -> path;
            case "getContextPath" -> "";
            case "toString" -> method+" "+path;
            default -> null;
        });
    }
    public static void main(String[] args) throws Exception {
        for(boolean enabled:List.of(true,false))try(var context=new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("probe",Map.of("bioagent.enabled",String.valueOf(enabled))));
            context.register(HostSecurity.class,WebsiteDownloadSecurity.class);context.refresh();
            if(context.containsBean("websiteDownloadChain")!=enabled)throw new AssertionError("Enable flag ignored");
            if(!enabled)continue;
            var chain=context.getBean("websiteDownloadChain",SecurityFilterChain.class);
            if(!chain.matches(request("GET","/assistant/received-download/test")))throw new AssertionError("Download not matched");
            for(String path:List.of("/assistant/received-ticket","/assistant/resources","/assistant/config","/assistant/received-download/a/b","/other"))
                if(chain.matches(request("GET",path)))throw new AssertionError("Host route intercepted: "+path);
            if(chain.matches(request("POST","/assistant/received-download/test")))throw new AssertionError("POST intercepted");
            var chains=context.getBeanProvider(SecurityFilterChain.class).orderedStream().toList();
            if(chains.size()!=2||chains.get(0)!=chain)throw new AssertionError("Incorrect chain order");
        }
        int[] status={0};var body=new StringWriter();
        var response=(HttpServletResponse)Proxy.newProxyInstance(HttpServletResponse.class.getClassLoader(),new Class<?>[]{HttpServletResponse.class},(p,m,a)-> {
            if(m.getName().equals("setStatus"))status[0]=(Integer)a[0];
            if(m.getName().equals("getWriter"))return new PrintWriter(body);
            return null;
        });
        new AssistantController(new ObjectMapper(),null,null,null,null).receivedDownload("invalid",response);
        if(status[0]!=401||!body.toString().contains("expired or already used"))throw new AssertionError("Invalid download ticket accepted");
        System.out.println("PASS narrow download chain, chain order, disabled adapter, protected host routes and invalid-ticket rejection");
    }
}
