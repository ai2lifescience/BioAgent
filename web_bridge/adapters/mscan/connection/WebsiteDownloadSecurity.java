package com.mscan.web.controller.common;

import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;

/** Only the one-use download ticket endpoint uses this chain; host security is unchanged. */
@Configuration(proxyBeanMethods=false)
@ConditionalOnProperty(name="bioagent.enabled",havingValue="true")
public class WebsiteDownloadSecurity {
    @Bean
    @Order(-1)
    public SecurityFilterChain websiteDownloadChain(HttpSecurity http) throws Exception {
        http.securityMatcher(new AntPathRequestMatcher("/assistant/received-download/*","GET"));
        // The controller consumes the expiring ticket and rechecks resource ownership.
        http.authorizeHttpRequests(auth->auth.anyRequest().permitAll());
        http.cors(Customizer.withDefaults());
        return http.build();
    }
}
