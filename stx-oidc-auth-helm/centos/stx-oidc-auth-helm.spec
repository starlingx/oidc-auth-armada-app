# Application tunables (maps to metadata)
%global app_name oidc-auth-apps
%global helm_repo stx-platform

# Install location
%global app_folder /usr/local/share/applications/helm

# Build variables
%global helm_folder /usr/lib/helm

# the dex chart tar name
%global dex_tar_name dex-0.8.2.tgz

Summary: The StarlingX K8S application for OIDC authorization
Name: stx-oidc-auth-helm
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: unknown

Source0: %{name}-%{version}.tar.gz

# a patch for secret observer
Patch01: 0001-move-metadata-release-for-helmv3.patch

# secret-observer source from stx/helm-charts/secret-observer
# plugin source from stx/oidc-auth-armada-app/python-k8sapp-oidc
# dex-helm source from stx/downloads/dex-0.8.2.tgz

BuildArch: noarch

BuildRequires: helm
BuildRequires: python-k8sapp-oidc
BuildRequires: python-k8sapp-oidc-wheels

%description
The StarlingX K8S application for OIDC authorization

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

# patch the dex chart
tar xf %{dex_tar_name}
rm %{dex_tar_name}
patch -p1 < files/0001-Create-new-config-value-extraStaticClients.patch
find dex -type f -print0 | xargs -0 tar zcf %{dex_tar_name}
rm -r dex

# Create a chart tarball compliant with sysinv kube-app.py
%define app_staging %{_builddir}/staging
%define app_tarball %{app_name}-%{version}-%{tis_patch_ver}.tgz
%define app_path %{_builddir}/%{app_tarball}

# Setup staging
mkdir -p %{app_staging}
cp files/metadata.yaml %{app_staging}
mkdir -p %{app_staging}/charts
cp helm-charts/*.tgz %{app_staging}/charts
cp dex*.tgz %{app_staging}/charts
cp -R fluxcd-manifests %{app_staging}/

# Copy the plugins: installed in the buildroot
mkdir -p %{app_staging}/plugins
cp /plugins/%{app_name}/*.whl %{app_staging}/plugins

cd %{app_staging}

# Populate metadata
sed -i 's/@APP_NAME@/%{app_name}/g' %{app_staging}/metadata.yaml
sed -i 's/@APP_VERSION@/%{version}-%{tis_patch_ver}/g' %{app_staging}/metadata.yaml
sed -i 's/@HELM_REPO@/%{helm_repo}/g' %{app_staging}/metadata.yaml

# calculate checksum of all files in app_staging
find . -type f ! -name '*.md5' -print0 | xargs -0 md5sum > checksum.md5
# package the app
tar -zcf %app_path -C %{app_staging}/ .

# switch back to source root
cd -

# Cleanup staging
rm -fr %{app_staging}

%install
install -d -m 755 %{buildroot}/%{app_folder}
install -p -D -m 755 %app_path %{buildroot}/%{app_folder}

%files
%defattr(-,root,root,-)
%{app_folder}/%{app_tarball}
