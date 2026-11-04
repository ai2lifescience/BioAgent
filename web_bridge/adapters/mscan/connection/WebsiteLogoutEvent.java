package com.mscan.web.controller.common;

/** The verified host identity, published before the host login is invalidated. */
public record WebsiteLogoutEvent(String userId) {}
