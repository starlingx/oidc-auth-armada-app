# Application tunables (maps to metadata)
%global app_name oidc-auth-apps
%global helm_repo stx-platform

# Install location
%global app_folder /usr/local/share/applications/helm

# Build variables
%global helm_folder /usr/lib/helm

Summary: StarlingX K8S application: OIDC authorization
Name: stx-oidc-auth-helm
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: unknown

Source0: %{name}-%{version}.tar.gz

Patch01: 0001-move-metadata-release-for-helmv3.patch

# secret-observer source from stx//helm-charts/secret-observer
# plugin source from stx/oidc-auth-armada-app/python-k8sapp-oidc
# dex-helm source from stx/oidc-auth-armada-app/dex-helm/ and:
# stx/downloads/helm-charts-92b6289ae93816717a8453cfe62bad51cbdb8ad0.tar.gz

BuildArch: noarch

BuildRequires: helm
BuildRequires: dex-helm
BuildRequires: python-k8sapp-oidc
BuildRequires: python-k8sapp-oidc-wheels
Requires: dex-helm

%description
The StarlingX K8S application for OIDC authorization

%package fluxcd
Summary: The StarlingX K8S Fluxcd application for OIDC authorization
Group: base
License: Apache-2.0

%description fluxcd
The StarlingX K8S Fluxcd application for OIDC authorization

%prep
%setup

%patch01 -p1

%build

# This chart does not require chartmuseum server since
# it has no dependency on local or stable repos.
# Make the charts. These produce a tgz file
cd helm-charts
make oidc-client
make secret-observer

# switch back to source root
cd -

# Create a chart tarball compliant with sysinv kube-app.py
%define app_staging %{_builddir}/staging
%define app_tarball_armada %{app_name}-%{version}-%{tis_patch_ver}.tgz
%define app_tarball_fluxcd %{app_name}-fluxcd-%{version}-%{tis_patch_ver}.tgz
%define armada_app_path %{_builddir}/%{app_tarball_armada}
%define fluxcd_app_path %{_builddir}/%{app_tarball_fluxcd}

# Setup staging
mkdir -p %{app_staging}
cp files/metadata.yaml %{app_staging}
cp manifests/manifest.yaml %{app_staging}
mkdir -p %{app_staging}/charts
cp helm-charts/*.tgz %{app_staging}/charts
cp %{helm_folder}/dex*.tgz %{app_staging}/charts

cd %{app_staging}

# Populate metadata
sed -i 's/@APP_NAME@/%{app_name}/g' %{app_staging}/metadata.yaml
sed -i 's/@APP_VERSION@/%{version}-%{tis_patch_ver}/g' %{app_staging}/metadata.yaml
sed -i 's/@HELM_REPO@/%{helm_repo}/g' %{app_staging}/metadata.yaml

# Copy the plugins: installed in the buildroot
mkdir -p %{app_staging}/plugins
cp /plugins/%{app_name}/*.whl %{app_staging}/plugins

# calculate checksum of all files in app_staging
find . -type f ! -name '*.md5' -print0 | xargs -0 md5sum > checksum.md5
# package armada app
tar -zcf %armada_app_path -C %{app_staging}/ .

# switch back to source root
cd -

# Prepare app_staging for fluxcd package
rm -f %{app_staging}/manifest.yaml

cp -R fluxcd-manifests %{app_staging}/

# calculate checksum of all files in app_staging
cd %{app_staging}
find . -type f ! -name '*.md5' -print0 | xargs -0 md5sum > checksum.md5
# package fluxcd app
tar -zcf %fluxcd_app_path -C %{app_staging}/ .

# switch back to source root
cd -

# Cleanup staging
rm -fr %{app_staging}

%install
install -d -m 755 %{buildroot}/%{app_folder}
install -p -D -m 755 %armada_app_path %{buildroot}/%{app_folder}
install -p -D -m 755 %fluxcd_app_path %{buildroot}/%{app_folder}

%files
%defattr(-,root,root,-)
%{app_folder}/%{app_tarball_armada}

%files fluxcd
%defattr(-,root,root,-)
%{app_folder}/%{app_tarball_fluxcd}
