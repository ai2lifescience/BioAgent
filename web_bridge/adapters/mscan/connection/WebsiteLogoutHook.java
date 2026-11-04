package com.mscan.web.controller.common;

import com.mscan.framework.web.service.TokenService;
import jakarta.servlet.http.HttpServletRequest;
import org.aspectj.lang.annotation.Aspect;
import org.aspectj.lang.annotation.Before;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Component;

/** Observe the existing host logout before its verified login is invalidated. */
@Aspect
@Component
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class WebsiteLogoutHook {
    private final ApplicationEventPublisher events;
    public WebsiteLogoutHook(ApplicationEventPublisher events) { this.events=events; }

    @Before(value="execution(* com.mscan.framework.web.service.TokenService+.invalidateSession(..)) && target(tokens) && args(request,..)",argNames="tokens,request")
    public void beforeLogout(TokenService tokens,HttpServletRequest request) {
        var user=tokens.getLoginUser(request);
        if(user!=null)events.publishEvent(new WebsiteLogoutEvent(user.getUserId()));
    }
}
