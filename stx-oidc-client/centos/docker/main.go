// Initial file was taken from https://github.com/dexidp/dex/tree/master/cmd/example-app 2019
//
// Copyright (c) 2020 Wind River Systems, Inc.
//
// SPDX-License-Identifier: Apache-2.0
//
package main

import (
    "bytes"
    "context"
    "crypto/tls"
    "crypto/x509"
    "encoding/json"
    "fmt"
    "io/ioutil"
    "log"
    "net"
    "net/http"
    "net/http/httputil"
    "net/url"
    "os"
    "strings"
    "time"

    "github.com/coreos/go-oidc"
    "github.com/spf13/cobra"
    "github.com/spf13/viper"
    "golang.org/x/oauth2"
)

const exampleAppState = "I wish to wash my irish wristwatch"

var (
    config_file string
    debug       bool
)

type app struct {
    clientID     string
    clientSecret string
    redirectURI  string

    verifier *oidc.IDTokenVerifier
    provider *oidc.Provider

    // Does the provider use "offline_access" scope to request a refresh token
    // or does it use "access_type=offline" (e.g. Google)?
    offlineAsScope bool

    client *http.Client
}

type Config struct {
    a         app
    issuerURL string
    listen    string
    tlsCert   string
    tlsKey    string
    rootCAs   string
    debug     bool
}

// return an HTTP client which trusts the provided root CAs.
func httpClientForRootCAs(rootCAs string) (*http.Client, error) {
    tlsConfig := tls.Config{RootCAs: x509.NewCertPool()}
    rootCABytes, err := ioutil.ReadFile(rootCAs)
    if err != nil {
        return nil, fmt.Errorf("failed to read root-ca: %v", err)
    }
    if !tlsConfig.RootCAs.AppendCertsFromPEM(rootCABytes) {
        return nil, fmt.Errorf("no certs found in root CA file %q", rootCAs)
    }
    return &http.Client{
        Transport: &http.Transport{
            TLSClientConfig: &tlsConfig,
            Proxy:           http.ProxyFromEnvironment,
            Dial: (&net.Dialer{
                Timeout:   30 * time.Second,
                KeepAlive: 30 * time.Second,
            }).Dial,
            TLSHandshakeTimeout:   10 * time.Second,
            ExpectContinueTimeout: 1 * time.Second,
        },
    }, nil
}

type debugTransport struct {
    t http.RoundTripper
}

func (d debugTransport) RoundTrip(req *http.Request) (*http.Response, error) {
    reqDump, err := httputil.DumpRequest(req, true)
    if err != nil {
        return nil, err
    }
    log.Printf("%s", reqDump)

    resp, err := d.t.RoundTrip(req)
    if err != nil {
        return nil, err
    }

    respDump, err := httputil.DumpResponse(resp, true)
    if err != nil {
        resp.Body.Close()
        return nil, err
    }
    log.Printf("%s", respDump)
    return resp, nil
}

func start_app(config Config) {
    u, err := url.Parse(config.a.redirectURI)
    if err != nil {
        log.Fatalf("parse redirect-uri: %v", err)
    }
    listenURL, err := url.Parse(config.listen)
    if err != nil {
        log.Fatalf("parse listen address: %v", err)
    }

    if config.rootCAs != "" {
        client, err := httpClientForRootCAs(config.rootCAs)
        if err != nil {
            log.Fatalf("Failed to parse a trusted cert: %v", err)
        }
        config.a.client = client
    }

    if debug {
        if config.a.client == nil {
            config.a.client = &http.Client{
                Transport: debugTransport{http.DefaultTransport},
            }
        } else {
            config.a.client.Transport = debugTransport{config.a.client.Transport}
        }
    }

    if config.a.client == nil {
        config.a.client = http.DefaultClient
    }

    ctx := oidc.ClientContext(context.Background(), config.a.client)
    provider, err := oidc.NewProvider(ctx, config.issuerURL)
    if err != nil {
        log.Fatalf("Failed to query provider %q: %v", config.issuerURL, err)
    }

    var s struct {
        ScopesSupported []string `json:"scopes_supported"`
    }
    if err := provider.Claims(&s); err != nil {
        log.Fatalf("Failed to parse provider scopes_supported: %v", err)
    }

    if len(s.ScopesSupported) == 0 {
        // scopes_supported is a "RECOMMENDED" discovery claim, not a required
        // one. If missing, assume that the provider follows the spec and has
        // an "offline_access" scope.
        config.a.offlineAsScope = true
    } else {
        // See if scopes_supported has the "offline_access" scope.
        config.a.offlineAsScope = func() bool {
            for _, scope := range s.ScopesSupported {
                if scope == oidc.ScopeOfflineAccess {
                    return true
                }
            }
            return false
        }()
    }

    config.a.provider = provider
    config.a.verifier = provider.Verifier(&oidc.Config{ClientID: config.a.clientID})

    http.HandleFunc("/", config.a.handleLogin)
    http.HandleFunc(u.Path, config.a.handleCallback)

    switch listenURL.Scheme {
    case "http":
        log.Printf("listening on %s", config.listen)
        http.ListenAndServe(listenURL.Host, nil)
    case "https":
        log.Printf("listening on %s", config.listen)
        http.ListenAndServeTLS(listenURL.Host, config.tlsCert, config.tlsKey, nil)
    default:
        fmt.Errorf("listen address %q is not using http or https", config.listen)
    }
}



var rootCmd = &cobra.Command{
    Use: "oidc-client",
    Short: "Dex Kubernetes Client",
    Long: "",
    Run: func(cmd *cobra.Command, args []string) {

        var config Config
        err := viper.Unmarshal(&config)
        if err != nil {
            log.Fatalf("Unable to decode configuration into struct, %v", err)
        }

        config.issuerURL = viper.GetString("issuer")
        config.listen = viper.GetString("listen")
        config.rootCAs = viper.GetString("issuer_root_ca")
        config.a.clientID = viper.GetString("client_id")
        config.a.clientSecret = viper.GetString("client_secret")
        config.a.redirectURI = viper.GetString("redirect_uri")
        log.Printf("config=%+v", config)

        // Start the app
        start_app(config)
    },
}

// Read in config file
func initConfig() {
    if config_file != "" {
        viper.SetConfigFile(config_file)
        viper.SetConfigType("yaml")

        // If a config file is found, read it in.
        if err := viper.ReadInConfig(); err != nil {
            log.Printf("Fatal error config file: %s \n", err)
        } else {
            log.Printf("using config file: %s", viper.ConfigFileUsed())
        }
    }
}

// Initialization
func init() {
    cobra.OnInitialize(initConfig)
    viper.BindPFlags(rootCmd.Flags())
    rootCmd.Flags().StringVar(&config_file, "config", "", "./config.yaml")
    rootCmd.PersistentFlags().BoolVarP(&debug, "debug", "d", false, "Enable debug logging")
}

func main() {
    if err := rootCmd.Execute(); err != nil {
        fmt.Fprintf(os.Stderr, "error: %v\n", err)
        os.Exit(2)
    }
}

func (a *app) oauth2Config(scopes []string) *oauth2.Config {
    return &oauth2.Config{
        ClientID:     a.clientID,
        ClientSecret: a.clientSecret,
        Endpoint:     a.provider.Endpoint(),
        Scopes:       scopes,
        RedirectURL:  a.redirectURI,
    }
}

func (a *app) handleLogin(w http.ResponseWriter, r *http.Request) {
    var scopes []string
    if extraScopes := r.FormValue("extra_scopes"); extraScopes != "" {
        scopes = strings.Split(extraScopes, " ")
    }
    var clients []string
    if crossClients := r.FormValue("cross_client"); crossClients != "" {
        clients = strings.Split(crossClients, " ")
    }
    for _, client := range clients {
        scopes = append(scopes, "audience:server:client_id:"+client)
    }
    connectorID := ""
    if id := r.FormValue("connector_id"); id != "" {
        connectorID = id
    }

    authCodeURL := ""
    scopes = append(scopes, "openid", "profile", "email")
    if a.offlineAsScope {
        scopes = append(scopes, "offline_access")
        authCodeURL = a.oauth2Config(scopes).AuthCodeURL(exampleAppState)
    } else {
        authCodeURL = a.oauth2Config(scopes).AuthCodeURL(exampleAppState, oauth2.AccessTypeOffline)
    }
    if connectorID != "" {
        authCodeURL = authCodeURL + "&connector_id=" + connectorID
    }
    http.Redirect(w, r, authCodeURL, http.StatusSeeOther)
}

func (a *app) handleCallback(w http.ResponseWriter, r *http.Request) {
    var (
        err   error
        token *oauth2.Token
    )
    log.Printf("In handleCallback")
    ctx := oidc.ClientContext(r.Context(), a.client)
    oauth2Config := a.oauth2Config(nil)
    switch r.Method {
    case http.MethodGet:
        // Authorization redirect callback from OAuth2 auth flow.
        if errMsg := r.FormValue("error"); errMsg != "" {
            http.Error(w, errMsg+": "+r.FormValue("error_description"), http.StatusBadRequest)
            return
        }
        code := r.FormValue("code")
        if code == "" {
            http.Error(w, fmt.Sprintf("no code in request: %q", r.Form), http.StatusBadRequest)
            return
        }
        if state := r.FormValue("state"); state != exampleAppState {
            http.Error(w, fmt.Sprintf("expected state %q got %q", exampleAppState, state), http.StatusBadRequest)
            return
        }
        token, err = oauth2Config.Exchange(ctx, code)
    case http.MethodPost:
        // Form request from frontend to refresh a token.
        refresh := r.FormValue("refresh_token")
        if refresh == "" {
            http.Error(w, fmt.Sprintf("no refresh_token in request: %q", r.Form), http.StatusBadRequest)
            return
        }
        t := &oauth2.Token{
            RefreshToken: refresh,
            Expiry:       time.Now().Add(-time.Hour),
        }
        token, err = oauth2Config.TokenSource(ctx, t).Token()
    default:
        http.Error(w, fmt.Sprintf("method not implemented: %s", r.Method), http.StatusBadRequest)
        return
    }

    if err != nil {
        http.Error(w, fmt.Sprintf("failed to get token: %v", err), http.StatusInternalServerError)
        return
    }

    rawIDToken, ok := token.Extra("id_token").(string)
    if !ok {
        http.Error(w, "no id_token in token response", http.StatusInternalServerError)
        return
    }

    idToken, err := a.verifier.Verify(r.Context(), rawIDToken)
    if err != nil {
        http.Error(w, fmt.Sprintf("failed to verify ID token: %v", err), http.StatusInternalServerError)
        return
    }

    accessToken, ok := token.Extra("access_token").(string)
    if !ok {
        http.Error(w, "no access_token in token response", http.StatusInternalServerError)
        return
    }

    var claims json.RawMessage
    if err := idToken.Claims(&claims); err != nil {
        http.Error(w, fmt.Sprintf("error decoding ID token claims: %v", err), http.StatusInternalServerError)
        return
    }

    buff := new(bytes.Buffer)
    if err := json.Indent(buff, []byte(claims), "", "  "); err != nil {
        http.Error(w, fmt.Sprintf("error indenting ID token claims: %v", err), http.StatusInternalServerError)
        return
    }

    renderToken(w, a.redirectURI, rawIDToken, accessToken, token.RefreshToken, buff.String())
}
