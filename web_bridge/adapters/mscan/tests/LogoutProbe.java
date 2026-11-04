import com.fasterxml.jackson.databind.ObjectMapper;
import com.mscan.web.controller.common.WebsiteLogoutHook;
import com.mscan.framework.web.service.TokenService;
import com.mscan.common.core.domain.model.LoginUser;
import org.springframework.aop.aspectj.annotation.AspectJProxyFactory;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import com.mscan.web.controller.common.AssistantController;
import com.mscan.web.controller.common.NativeResultResources;
import java.lang.reflect.Proxy;
import java.util.Arrays;
import com.sun.net.httpserver.HttpServer;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.core.env.MapPropertySource;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

/** Check real Spring event delivery and the controller's outbound HTTP request. */
public class LogoutProbe {
    public static class Tokens extends TokenService {
        boolean invalidated;
        LoginUser login;
        @Override public LoginUser getLoginUser(HttpServletRequest request) { return invalidated?null:login; }
        @Override public void invalidateSession(HttpServletRequest request,HttpServletResponse response) { invalidated=true; }
    }
    public static void main(String[] args) throws Exception {
        String secret = UUID.randomUUID().toString() + UUID.randomUUID();
        AtomicBoolean called = new AtomicBoolean();
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        server.createContext("/website/service/revoke", exchange -> {
            var body = new ObjectMapper().readTree(exchange.getRequestBody());
            boolean valid = exchange.getRequestMethod().equals("POST")
                    && ("Bearer " + secret).equals(exchange.getRequestHeaders().getFirst("Authorization"))
                    && "mscan".equals(exchange.getRequestHeaders().getFirst("X-Website-Site"))
                    && "verified-host-user".equals(body.path("subject").asText());
            called.set(valid);
            byte[] reply = "{\"revoked\":true}".getBytes(StandardCharsets.UTF_8);
            exchange.sendResponseHeaders(valid ? 200 : 400, reply.length);
            exchange.getResponseBody().write(reply); exchange.close();
        });
        server.start();
        try (var context = new AnnotationConfigApplicationContext()) {
            context.getEnvironment().getPropertySources().addFirst(new MapPropertySource("probe", Map.of(
                    "bioagent.enabled", "true", "bioagent.secret", secret,
                    "bioagent.url", "http://127.0.0.1:" + server.getAddress().getPort())));
            // Satisfy the controller's resource dependency without querying a database.
            var constructor=NativeResultResources.class.getConstructors()[0];
            Object[] dependencies=Arrays.stream(constructor.getParameterTypes()).map(type ->
                type==ObjectMapper.class ? new ObjectMapper() : Proxy.newProxyInstance(type.getClassLoader(),new Class<?>[]{type},(proxy,method,values)-> {
                    throw new AssertionError("Logout unexpectedly accessed native data: "+method.getName());
                })).toArray();
            var resources=(NativeResultResources)constructor.newInstance(dependencies);
            context.registerBean(NativeResultResources.class,()->resources);
            context.registerBean(AssistantController.class,
                    () -> new AssistantController(new ObjectMapper(), null, null, null, null));
            context.refresh();
            var target=new Tokens();target.login=new LoginUser();target.login.setUserId("verified-host-user");
            var factory=new AspectJProxyFactory(target);
            factory.addAspect(new WebsiteLogoutHook(event->{
                if(target.invalidated)throw new AssertionError("Revocation ran after host invalidation");
                context.publishEvent(event);
            }));
            TokenService tokens=factory.getProxy();
            tokens.invalidateSession(null,null);
            if(!target.invalidated)throw new AssertionError("Host logout did not complete");
            if (!called.get()) throw new AssertionError("Logout event did not revoke the verified host subject");
            called.set(false);target.invalidated=false;target.login=null;
            tokens.invalidateSession(null,null);
            if(called.get()||!target.invalidated)throw new AssertionError("Anonymous logout changed");
            System.out.println("PASS: Adapter logout hook revokes verified identity before invalidation; anonymous logout completes.");
        } finally { server.stop(0); }
    }
}
