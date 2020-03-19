# Application tunables (maps to metadata)
%global app_name oidc-auth-apps
%global helm_repo stx-platform

# Install location
%global app_folder /usr/local/share/applications/helm

# Build variables
%global helm_folder /usr/lib/helm

%global sha 92b6289ae93816717a8453cfe62bad51cbdb8ad0

Summary: StarlingX OIDC auth Helm charts
Name: dex-helm
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: unknown

Source0: helm-charts-%{sha}.tar.gz
Source1: repositories.yaml
Source2: index.yaml
Source3: Makefile

Patch01: 0001-Update-Dex-chart-for-Kubernetes-API-1.16.patch
Patch02: 0002-add-image-pull-secrets.patch
Patch03: 0003-Add-affinity-support.patch

BuildArch: noarch

BuildRequires: helm

%description
StarlingX OIDC auth Helm charts

%prep
#%setup
%setup -n helm-charts
%patch01 -p1
%patch02 -p1
%patch03 -p1

%build
# initialize helm
# helm init --client-only does not work if there is no networking
# The following commands do essentially the same as: helm init
%define helm_home  %{getenv:HOME}/.helm
mkdir  %{helm_home}
mkdir  %{helm_home}/repository
mkdir  %{helm_home}/repository/cache
mkdir  %{helm_home}/repository/local
mkdir  %{helm_home}/plugins
mkdir  %{helm_home}/starters
mkdir  %{helm_home}/cache
mkdir  %{helm_home}/cache/archive

# Stage a repository file that only has a local repo
cp %{SOURCE1} %{helm_home}/repository/repositories.yaml

# Stage a local repo index that can be updated by the build
cp %{SOURCE2} %{helm_home}/repository/local/index.yaml

# Make the charts. These produce a tgz file
cp %{SOURCE3} stable
which make
cd stable
make dex
cd -

%install
install -d -m 755 ${RPM_BUILD_ROOT}%{helm_folder}
install -p -D -m 755 stable/*.tgz ${RPM_BUILD_ROOT}%{helm_folder}


%files
%defattr(-,root,root,-)
%{helm_folder}/*
