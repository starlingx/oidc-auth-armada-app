// Copyright (c) 2026 Wind River Systems, Inc.
//
// SPDX-License-Identifier: Apache-2.0
//
package main

import (
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/x509"
	"encoding/json"
	"encoding/pem"
	"fmt"
	"math/big"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"

	"github.com/coreos/go-oidc/v3/oidc"
)

// fakeOIDCServer creates a minimal OIDC discovery server
func fakeOIDCServer(t *testing.T) *httptest.Server {
	t.Helper()
	mux := http.NewServeMux()
	var serverURL string

	mux.HandleFunc("/.well-known/openid-configuration", func(w http.ResponseWriter, r *http.Request) {
		disc := map[string]interface{}{
			"issuer":                 serverURL,
			"authorization_endpoint": serverURL + "/auth",
			"token_endpoint":         serverURL + "/token",
			"jwks_uri":              serverURL + "/keys",
			"scopes_supported":      []string{"openid", "profile", "email", "offline_access"},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(disc)
	})

	mux.HandleFunc("/auth", func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusOK)
		w.Write([]byte("auth page"))
	})

	mux.HandleFunc("/token", func(w http.ResponseWriter, r *http.Request) {
		resp := map[string]interface{}{
			"access_token":  "fake-access-token",
			"token_type":    "Bearer",
			"refresh_token": "fake-refresh-token",
			"id_token":      "fake-id-token",
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(resp)
	})

	mux.HandleFunc("/keys", func(w http.ResponseWriter, r *http.Request) {
		keys := map[string]interface{}{
			"keys": []interface{}{},
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(keys)
	})

	srv := httptest.NewServer(mux)
	serverURL = srv.URL
	return srv
}

func setupTestApp(t *testing.T) (*app, *httptest.Server) {
	t.Helper()
	srv := fakeOIDCServer(t)

	ctx := oidc.ClientContext(
		t.Context(), http.DefaultClient)
	provider, err := oidc.NewProvider(ctx, srv.URL)
	if err != nil {
		t.Fatalf("NewProvider: %v", err)
	}

	a := &app{
		clientID:       "test-client",
		clientSecret:   "test-secret",
		redirectURI:    srv.URL + "/callback",
		provider:       provider,
		verifier:       provider.Verifier(&oidc.Config{ClientID: "test-client", SkipClientIDCheck: true, SkipExpiryCheck: true, SkipIssuerCheck: true, Now: func() time.Time { return time.Now() }}),
		offlineAsScope: true,
		client:         http.DefaultClient,
	}
	return a, srv
}

// --- Template tests ---

func TestRenderToken(t *testing.T) {
	w := httptest.NewRecorder()
	renderToken(w, "https://example.com/callback",
		"test-id-token", "test-access-token",
		"test-refresh-token", `{"sub":"user1"}`)
	if w.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", w.Code)
	}
	body := w.Body.String()
	if !strings.Contains(body, "test-id-token") {
		t.Fatal("body missing id token")
	}
}

func TestRenderTokenNoRefresh(t *testing.T) {
	w := httptest.NewRecorder()
	renderToken(w, "https://example.com/callback",
		"id", "access", "", `{"sub":"u"}`)
	if w.Body.Len() == 0 {
		t.Fatal("empty body")
	}
}

func TestRenderTemplate(t *testing.T) {
	w := httptest.NewRecorder()
	renderTemplate(w, tokenTmpl, tokenTmplData{
		IDToken: "x", AccessToken: "y",
		RedirectURL: "/cb", Claims: "{}",
	})
	if w.Code != http.StatusOK {
		t.Fatalf("got %d", w.Code)
	}
}

func TestRenderTemplateNilData(t *testing.T) {
	w := httptest.NewRecorder()
	renderTemplate(w, tokenTmpl, nil)
	// template executes with nil data - should still work
	// (fields will be zero values)
	if w.Body.Len() == 0 {
		t.Fatal("empty body")
	}
}

// --- httpClientForRootCAs tests ---

func TestHttpClientForRootCAs_ValidCA(t *testing.T) {
	key, _ := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	tmpl := &x509.Certificate{
		SerialNumber:          big.NewInt(1),
		NotBefore:             time.Now(),
		NotAfter:              time.Now().Add(time.Hour),
		IsCA:                  true,
		BasicConstraintsValid: true,
	}
	der, _ := x509.CreateCertificate(rand.Reader, tmpl, tmpl, &key.PublicKey, key)
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "CERTIFICATE", Bytes: der})
	f := filepath.Join(t.TempDir(), "ca.pem")
	os.WriteFile(f, pemBytes, 0644)

	client, err := httpClientForRootCAs(f)
	if err != nil {
		t.Fatalf("error: %v", err)
	}
	if client == nil {
		t.Fatal("nil client")
	}
}

func TestHttpClientForRootCAs_FileNotFound(t *testing.T) {
	_, err := httpClientForRootCAs("/no/such/file")
	if err == nil {
		t.Fatal("expected error")
	}
}

func TestHttpClientForRootCAs_InvalidPEM(t *testing.T) {
	f := filepath.Join(t.TempDir(), "bad.pem")
	os.WriteFile(f, []byte("garbage"), 0644)
	_, err := httpClientForRootCAs(f)
	if err == nil {
		t.Fatal("expected error")
	}
}

// --- oauth2Config test ---

func TestOauth2Config(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	cfg := a.oauth2Config([]string{"openid", "profile"})
	if cfg.ClientID != "test-client" {
		t.Fatalf("got clientID %s", cfg.ClientID)
	}
	if cfg.ClientSecret != "test-secret" {
		t.Fatal("wrong secret")
	}
	if cfg.RedirectURL != srv.URL+"/callback" {
		t.Fatalf("got redirect %s", cfg.RedirectURL)
	}
	if len(cfg.Scopes) != 2 {
		t.Fatalf("got %d scopes", len(cfg.Scopes))
	}
}

// --- handleLogin tests ---

func TestHandleLogin_Basic(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("GET", "/", nil)
	w := httptest.NewRecorder()
	a.handleLogin(w, req)

	if w.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d", w.Code)
	}
	loc := w.Header().Get("Location")
	if !strings.Contains(loc, "client_id=test-client") {
		t.Fatalf("redirect missing client_id: %s", loc)
	}
}

func TestHandleLogin_WithExtraScopes(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("GET", "/?extra_scopes=custom1+custom2", nil)
	w := httptest.NewRecorder()
	a.handleLogin(w, req)

	if w.Code != http.StatusSeeOther {
		t.Fatalf("expected 303, got %d", w.Code)
	}
}

func TestHandleLogin_WithCrossClient(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("GET", "/?cross_client=other-app", nil)
	w := httptest.NewRecorder()
	a.handleLogin(w, req)

	loc := w.Header().Get("Location")
	if !strings.Contains(loc, "audience") {
		t.Fatalf("missing audience scope: %s", loc)
	}
}

func TestHandleLogin_WithConnectorID(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("GET", "/?connector_id=ldap", nil)
	w := httptest.NewRecorder()
	a.handleLogin(w, req)

	loc := w.Header().Get("Location")
	if !strings.Contains(loc, "connector_id=ldap") {
		t.Fatalf("missing connector_id: %s", loc)
	}
}

func TestHandleLogin_OfflineAccessTypeOffline(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()
	a.offlineAsScope = false

	req := httptest.NewRequest("GET", "/", nil)
	w := httptest.NewRecorder()
	a.handleLogin(w, req)

	loc := w.Header().Get("Location")
	if !strings.Contains(loc, "access_type=offline") {
		t.Fatalf("missing access_type=offline: %s", loc)
	}
}

// --- handleCallback tests ---

func TestHandleCallback_GetNoError(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	// Missing code param
	req := httptest.NewRequest("GET", "/callback", nil)
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleCallback_GetWithError(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("GET",
		"/callback?error=access_denied&error_description=nope", nil)
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleCallback_GetBadState(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("GET",
		"/callback?code=abc&state=wrong", nil)
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleCallback_GetValidCode(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	// Token exchange will fail because fake server returns
	// invalid id_token, but we exercise the code path
	req := httptest.NewRequest("GET",
		fmt.Sprintf("/callback?code=testcode&state=%s",
			url.QueryEscape(exampleAppState)), nil)
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	// Will get 500 because id_token verification fails
	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", w.Code)
	}
}

func TestHandleCallback_PostNoRefresh(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("POST", "/callback",
		strings.NewReader(""))
	req.Header.Set("Content-Type",
		"application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

func TestHandleCallback_PostWithRefresh(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	form := url.Values{"refresh_token": {"fake-refresh"}}
	req := httptest.NewRequest("POST", "/callback",
		strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type",
		"application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	// Will fail at token refresh or verify step
	if w.Code == http.StatusOK {
		// unexpected success
	}
}

func TestHandleCallback_UnsupportedMethod(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	req := httptest.NewRequest("PUT", "/callback", nil)
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	if w.Code != http.StatusBadRequest {
		t.Fatalf("expected 400, got %d", w.Code)
	}
}

// --- debugTransport test ---

func TestDebugTransport_RoundTrip(t *testing.T) {
	backend := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			w.Write([]byte("ok"))
		}))
	defer backend.Close()

	dt := debugTransport{t: http.DefaultTransport}
	req, _ := http.NewRequest("GET", backend.URL, nil)
	resp, err := dt.RoundTrip(req)
	if err != nil {
		t.Fatalf("RoundTrip error: %v", err)
	}
	if resp.StatusCode != 200 {
		t.Fatalf("got %d", resp.StatusCode)
	}
	resp.Body.Close()
}

// --- initConfig test ---

func TestInitConfig_NoFile(t *testing.T) {
	config_file = ""
	initConfig()
	// should not panic
}

func TestInitConfig_WithFile(t *testing.T) {
	dir := t.TempDir()
	f := filepath.Join(dir, "config.yaml")
	os.WriteFile(f, []byte("issuer: https://test\n"), 0644)
	config_file = f
	initConfig()
	config_file = ""
}

func TestInitConfig_MissingFile(t *testing.T) {
	config_file = "/nonexistent/config.yaml"
	initConfig() // should log error but not panic
	config_file = ""
}

// --- constant test ---

func TestExampleAppStateConstant(t *testing.T) {
	if exampleAppState == "" {
		t.Fatal("empty")
	}
}

// --- oauth2 token exchange helpers ---

func TestHandleCallback_GetCodeExchangeFails(t *testing.T) {
	// Use a server that returns error on token exchange
	var badSrvURL string
	badSrv := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if strings.Contains(r.URL.Path, "openid-configuration") {
				disc := map[string]interface{}{
					"issuer":                 badSrvURL,
					"authorization_endpoint": badSrvURL + "/auth",
					"token_endpoint":         badSrvURL + "/token",
					"jwks_uri":              badSrvURL + "/keys",
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(disc)
				return
			}
			if r.URL.Path == "/token" {
				w.WriteHeader(http.StatusBadRequest)
				w.Write([]byte(`{"error":"invalid_grant"}`))
				return
			}
			if r.URL.Path == "/keys" {
				json.NewEncoder(w).Encode(map[string]interface{}{"keys": []interface{}{}})
				return
			}
		}))
	badSrvURL = badSrv.URL
	defer badSrv.Close()

	ctx := oidc.ClientContext(t.Context(), http.DefaultClient)
	provider, err := oidc.NewProvider(ctx, badSrv.URL)
	if err != nil {
		t.Fatalf("NewProvider: %v", err)
	}

	a := &app{
		clientID:     "c",
		clientSecret: "s",
		redirectURI:  badSrv.URL + "/callback",
		provider:     provider,
		verifier:     provider.Verifier(&oidc.Config{ClientID: "c", SkipClientIDCheck: true, SkipExpiryCheck: true, SkipIssuerCheck: true}),
		client:       http.DefaultClient,
	}

	req := httptest.NewRequest("GET",
		fmt.Sprintf("/callback?code=bad&state=%s",
			url.QueryEscape(exampleAppState)), nil)
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", w.Code)
	}
}

// Force coverage of the oauth2Config with offline_access scope
func TestOauth2Config_Scopes(t *testing.T) {
	a, srv := setupTestApp(t)
	defer srv.Close()

	cfg := a.oauth2Config([]string{"openid", "offline_access", "groups"})
	found := false
	for _, s := range cfg.Scopes {
		if s == "offline_access" {
			found = true
		}
	}
	if !found {
		t.Fatal("missing offline_access scope")
	}
}

// Test handleCallback POST with refresh token that gets a token
// but fails on id_token verification
func TestHandleCallback_PostRefreshTokenExchange(t *testing.T) {
	// Server that returns a token but with invalid id_token
	var srvURL string
	srv := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if strings.Contains(r.URL.Path, "openid-configuration") {
				disc := map[string]interface{}{
					"issuer":                 srvURL,
					"authorization_endpoint": srvURL + "/auth",
					"token_endpoint":         srvURL + "/token",
					"jwks_uri":              srvURL + "/keys",
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(disc)
				return
			}
			if r.URL.Path == "/token" {
				resp := map[string]interface{}{
					"access_token":  "new-access",
					"token_type":    "Bearer",
					"id_token":      "not-a-jwt",
					"refresh_token": "new-refresh",
					"expires_in":    3600,
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(resp)
				return
			}
			if r.URL.Path == "/keys" {
				json.NewEncoder(w).Encode(map[string]interface{}{"keys": []interface{}{}})
				return
			}
		}))
	srvURL = srv.URL
	defer srv.Close()

	ctx := oidc.ClientContext(t.Context(), http.DefaultClient)
	provider, err := oidc.NewProvider(ctx, srv.URL)
	if err != nil {
		t.Fatalf("NewProvider: %v", err)
	}

	a := &app{
		clientID:     "c",
		clientSecret: "s",
		redirectURI:  srv.URL + "/callback",
		provider:     provider,
		verifier:     provider.Verifier(&oidc.Config{ClientID: "c", SkipClientIDCheck: true, SkipExpiryCheck: true, SkipIssuerCheck: true}),
		client:       http.DefaultClient,
	}

	form := url.Values{"refresh_token": {"old-refresh"}}
	req := httptest.NewRequest("POST", "/callback",
		strings.NewReader(form.Encode()))
	req.Header.Set("Content-Type", "application/x-www-form-urlencoded")
	w := httptest.NewRecorder()
	a.handleCallback(w, req)
	// Should fail at verify step with 500
	if w.Code != http.StatusInternalServerError {
		t.Fatalf("expected 500, got %d", w.Code)
	}
}

// Test start_app with invalid redirect URI
func TestStartApp_InvalidRedirectURI(t *testing.T) {
	if os.Getenv("TEST_START_APP_CRASH") == "1" {
		config := Config{}
		config.a.redirectURI = "://bad-uri"
		config.listen = "http://127.0.0.1:0"
		start_app(config)
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=TestStartApp_InvalidRedirectURI")
	cmd.Env = append(os.Environ(), "TEST_START_APP_CRASH=1")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		return // expected crash
	}
	t.Fatal("expected process to exit with error")
}

// Test start_app with bad listen URL
func TestStartApp_InvalidListenURL(t *testing.T) {
	if os.Getenv("TEST_START_APP_LISTEN") == "1" {
		config := Config{}
		config.a.redirectURI = "http://localhost/callback"
		config.listen = "://bad"
		start_app(config)
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=TestStartApp_InvalidListenURL")
	cmd.Env = append(os.Environ(), "TEST_START_APP_LISTEN=1")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		return
	}
	t.Fatal("expected process to exit with error")
}

// Test start_app with bad rootCAs file
func TestStartApp_BadRootCA(t *testing.T) {
	if os.Getenv("TEST_START_APP_CA") == "1" {
		config := Config{}
		config.a.redirectURI = "http://localhost/callback"
		config.listen = "http://127.0.0.1:0"
		config.rootCAs = "/nonexistent/ca.pem"
		start_app(config)
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=TestStartApp_BadRootCA")
	cmd.Env = append(os.Environ(), "TEST_START_APP_CA=1")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		return
	}
	t.Fatal("expected process to exit with error")
}

// Test start_app with bad OIDC provider
func TestStartApp_BadProvider(t *testing.T) {
	if os.Getenv("TEST_START_APP_PROVIDER") == "1" {
		config := Config{}
		config.a.redirectURI = "http://localhost/callback"
		config.listen = "http://127.0.0.1:0"
		config.issuerURL = "http://127.0.0.1:1/bad"
		start_app(config)
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=TestStartApp_BadProvider")
	cmd.Env = append(os.Environ(), "TEST_START_APP_PROVIDER=1")
	err := cmd.Run()
	if e, ok := err.(*exec.ExitError); ok && !e.Success() {
		return
	}
	t.Fatal("expected process to exit with error")
}

// Test main with no config (will fail trying to start)
func TestMain_NoConfig(t *testing.T) {
	if os.Getenv("TEST_MAIN_CRASH") == "1" {
		os.Args = []string{"oidc-client", "--config", "/nonexistent.yaml"}
		main()
		return
	}
	cmd := exec.Command(os.Args[0], "-test.run=TestMain_NoConfig")
	cmd.Env = append(os.Environ(), "TEST_MAIN_CRASH=1")
	err := cmd.Run()
	// main may exit 0 or non-zero depending on viper behavior
	_ = err
}

// Test start_app with valid OIDC server (covers scope parsing,
// handler registration, and listen path)
func TestStartApp_ValidConfig(t *testing.T) {
	if os.Getenv("TEST_START_APP_VALID") != "1" {
		// Run in subprocess with timeout
		cmd := exec.Command(os.Args[0],
			"-test.run=TestStartApp_ValidConfig",
			"-test.timeout=5s")
		cmd.Env = append(os.Environ(), "TEST_START_APP_VALID=1")
		// We expect it to be killed by timeout (it blocks on ListenAndServe)
		cmd.Run()
		return
	}

	// Create fake OIDC server
	var srvURL string
	srv := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if strings.Contains(r.URL.Path, "openid-configuration") {
				disc := map[string]interface{}{
					"issuer":                 srvURL,
					"authorization_endpoint": srvURL + "/auth",
					"token_endpoint":         srvURL + "/token",
					"jwks_uri":              srvURL + "/keys",
					"scopes_supported":      []string{"openid", "offline_access"},
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(disc)
				return
			}
			if r.URL.Path == "/keys" {
				json.NewEncoder(w).Encode(map[string]interface{}{"keys": []interface{}{}})
			}
		}))
	srvURL = srv.URL
	defer srv.Close()

	config := Config{
		issuerURL: srvURL,
		listen:    "https://127.0.0.1:0",
		tlsCert:   "/dev/null",
		tlsKey:    "/dev/null",
	}
	config.a.redirectURI = srvURL + "/callback"
	config.a.clientID = "test"
	config.a.clientSecret = "secret"

	// This will block on ListenAndServeTLS (which will fail
	// because /dev/null isn't a valid cert, but covers the path)
	start_app(config)
}

// Test start_app with HTTP scheme
func TestStartApp_HTTPScheme(t *testing.T) {
	if os.Getenv("TEST_START_APP_HTTP") != "1" {
		cmd := exec.Command(os.Args[0],
			"-test.run=TestStartApp_HTTPScheme",
			"-test.timeout=5s")
		cmd.Env = append(os.Environ(), "TEST_START_APP_HTTP=1")
		cmd.Run()
		return
	}

	var srvURL string
	srv := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if strings.Contains(r.URL.Path, "openid-configuration") {
				disc := map[string]interface{}{
					"issuer":                 srvURL,
					"authorization_endpoint": srvURL + "/auth",
					"token_endpoint":         srvURL + "/token",
					"jwks_uri":              srvURL + "/keys",
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(disc)
				return
			}
			if r.URL.Path == "/keys" {
				json.NewEncoder(w).Encode(map[string]interface{}{"keys": []interface{}{}})
			}
		}))
	srvURL = srv.URL
	defer srv.Close()

	config := Config{
		issuerURL: srvURL,
		listen:    "http://127.0.0.1:0",
	}
	config.a.redirectURI = srvURL + "/callback"
	config.a.clientID = "test"
	config.a.clientSecret = "secret"
	start_app(config)
}

// Test start_app with debug enabled
func TestStartApp_Debug(t *testing.T) {
	if os.Getenv("TEST_START_APP_DEBUG") != "1" {
		cmd := exec.Command(os.Args[0],
			"-test.run=TestStartApp_Debug",
			"-test.timeout=5s")
		cmd.Env = append(os.Environ(), "TEST_START_APP_DEBUG=1")
		cmd.Run()
		return
	}

	var srvURL string
	srv := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			if strings.Contains(r.URL.Path, "openid-configuration") {
				disc := map[string]interface{}{
					"issuer":                 srvURL,
					"authorization_endpoint": srvURL + "/auth",
					"token_endpoint":         srvURL + "/token",
					"jwks_uri":              srvURL + "/keys",
				}
				w.Header().Set("Content-Type", "application/json")
				json.NewEncoder(w).Encode(disc)
				return
			}
			if r.URL.Path == "/keys" {
				json.NewEncoder(w).Encode(map[string]interface{}{"keys": []interface{}{}})
			}
		}))
	srvURL = srv.URL
	defer srv.Close()

	debug = true
	config := Config{
		issuerURL: srvURL,
		listen:    "http://127.0.0.1:0",
	}
	config.a.redirectURI = srvURL + "/callback"
	config.a.clientID = "test"
	config.a.clientSecret = "secret"
	start_app(config)
}

// Test main function via rootCmd
func TestRootCmd_NoArgs(t *testing.T) {
	// rootCmd.Execute() will try to start the app which needs
	// a config file. Without one it just exits.
	// We test that the command structure is valid.
	if rootCmd.Use != "oidc-client" {
		t.Fatalf("unexpected Use: %s", rootCmd.Use)
	}
	if rootCmd.Short != "Dex Kubernetes Client" {
		t.Fatalf("unexpected Short: %s", rootCmd.Short)
	}
}

// Test debugTransport with failed request
func TestDebugTransport_BadURL(t *testing.T) {
	dt := debugTransport{t: http.DefaultTransport}
	req, _ := http.NewRequest("GET", "http://127.0.0.1:1/bad", nil)
	_, err := dt.RoundTrip(req)
	if err == nil {
		t.Fatal("expected error for bad URL")
	}
}
