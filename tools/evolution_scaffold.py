"""Generate independent reconstructed table adapters in both physical layouts."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def paths(root, layout, version):
    base = root / layout / version
    if layout == 'horizontal':
        return base/'table/csharp', base/'table/rust', base/'table/tests'
    return base/'csharp/table', base/'rust/table', base/'tests/table'


def templates(root=ROOT):
    profiles = json.loads((root/'evolution/profiles.json').read_text(encoding='utf-8'))['profiles']
    cs = (root/'evolution/templates/Adapter.cs').read_text(encoding='utf-8')
    rs = (root/'evolution/templates/adapter.rs').read_text(encoding='utf-8')
    fixtures = (root/'evolution/fixtures/corpus.json').read_text(encoding='utf-8')
    files = {}
    for layout in ['horizontal','vertical']:
        for p in profiles:
            csharp,rust,tests = paths(root,layout,p['version'])
            solution = csharp.parent/'RFX.slnx' if layout=='vertical' else root/layout/p['version']/'RFX.slnx'
            project_path = 'table/Table.csproj' if layout=='vertical' else 'table/csharp/Table.csproj'
            files[solution] = f'<Solution>\n  <Project Path="{project_path}" />\n</Solution>\n'
            files[csharp/'Adapter.cs'] = cs
            files[csharp/'Profile.cs'] = f'static class Profile {{ public static readonly int Level = {p["level"]}; }}\n'
            files[csharp/'Table.csproj'] = f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <DemoFramework Condition="'$(DemoFramework)' == ''">net8.0</DemoFramework>
    <TargetFramework>$(DemoFramework)</TargetFramework>
    <Version>{p['version']}</Version><AssemblyName>Table</AssemblyName>
    <Nullable>enable</Nullable><ImplicitUsings>enable</ImplicitUsings>
    <TreatWarningsAsErrors>true</TreatWarningsAsErrors>
  </PropertyGroup>
</Project>
'''
            files[rust/'src/main.rs'] = rs
            files[rust/'src/profile.rs'] = f'pub const LEVEL: usize = {p["level"]};\n'
            files[rust/'Cargo.toml'] = f'''[package]
name = "table-demo"
version = "{p['version']}"
edition = "2024"

[workspace]

[dependencies]
serde = "=1.0.219"
serde_json = {{ version = "=1.0.140", features = ["float_roundtrip"] }}
'''
            files[tests/'corpus.json'] = fixtures
            files[tests/'release.json'] = json.dumps(p,indent=2)+'\n'
    return files


def sync(root=ROOT, check=False):
    drift=[]
    for path, content in templates(root).items():
        if not path.exists() or path.read_text(encoding='utf-8')!=content:
            drift.append(str(path.relative_to(root)))
            if not check:
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(content,encoding='utf-8',newline='\n')
    return drift


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    drift=sync(check=args.check)
    print(f'{len(drift)} generated files {"differ" if args.check else "updated"}.')
    if args.check and drift:
        print('\n'.join(drift))
        raise SystemExit(1)
