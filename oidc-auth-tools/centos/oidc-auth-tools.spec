%global pypi_name oidcauthtools

Summary: OIDC authentication tool package
Name: %{pypi_name}
Version: 1.0
Release: %{tis_patch_ver}%{?_tis_dist}
License: Apache-2.0
Group: base
Packager: Wind River <info@windriver.com>
URL: unknown
BuildArch: noarch
Source: %name-%version.tar.gz

BuildRequires: python3-pbr >= 2.0.0
BuildRequires: python3-setuptools
BuildRequires: python3-wheel

Requires: python3-mechanize
Requires: python3-html5lib
Requires: python3-webencodings
Requires: python3-pbr >= 2.0.0


%description
This package contains OIDC authentication tools to obtain token
from DEX and setup kubernetes credential for a user.

%define local_bindir /usr/bin/
%define pythonroot /usr/lib/python3.6/site-packages


%prep
%setup

# Remove bundled egg-info
rm -rf *.egg-info

%build
export PBR_VERSION=%{version}
%{__python3} setup.py build
%py3_build_wheel

%install
export PBR_VERSION=%{version}
%{__python3} setup.py install --root=$RPM_BUILD_ROOT \
                             --install-lib=%{pythonroot} \
                             --prefix=/usr \
                             --install-data=/usr/share \
                             --single-version-externally-managed
mkdir -p $RPM_BUILD_ROOT/wheels
install -m 644 dist/*.whl $RPM_BUILD_ROOT/wheels/

%global _buildsubdir %{_builddir}/%{name}-%{version}
install -d 755 %{buildroot}%{local_bindir}

%clean
rm -rf $RPM_BUILD_ROOT

%files
%license LICENSE
%defattr(-,root,root,-)
/usr/bin/*
%{python3_sitelib}/oidcauthtools
%{python3_sitelib}/*.egg-info


%package wheels
Summary: %{name} wheels

%description wheels
Contains python wheels for %{name}

%files wheels
/wheels/*
