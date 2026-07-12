"""
企业定制版自动化构建脚本

用法:
    python scripts/build_enterprise.py --customer-name "XX公司" --logo path/to/logo.png --terms path/to/terms.csv

流程:
    1. 读取客户配置
    2. 生成 enterprise/profile.json + terms.csv + logo.png
    3. 运行 PyInstaller 构建 exe
    4. 拷贝企业配置到输出目录
    5. 运行 Inno Setup 生成安装包

依赖:
    pip install pyinstaller
    Inno Setup 6+ (iscc.exe 需在 PATH 或通过 --iscc-path 指定)
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILE = PROJECT_ROOT / "本地资料脱敏工具.spec"
DEFAULT_OUTPUT = PROJECT_ROOT / "dist"
CONTACT_EMAIL = "yilinwanxiang@163.com"
COMPANY_NAME = "艺林万象（北京）科技有限公司"
DEFAULT_TERMS_TEMPLATE = [
    {"value": "{customer_name}", "entity": "ORGANIZATION", "category": "企业名称", "note": "企业全称"},
    {"value": "{customer_short_name}", "entity": "ORGANIZATION", "category": "企业简称", "note": "企业简称"},
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="企业定制版自动化构建脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--customer-name", required=True, help="客户企业全称（必填）")
    parser.add_argument("--customer-short-name", default="", help="客户企业简称（默认取全称）")
    parser.add_argument("--product-name", default="本地资料脱敏工具", help="产品显示名称")
    parser.add_argument("--edition-name", default="企业专属版", help="版本名称")
    parser.add_argument("--logo", default="", help="客户 Logo PNG 文件路径")
    parser.add_argument("--terms", default="", help="企业敏感词库 CSV/TXT 文件路径")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT), help="输出目录（默认: dist）")
    parser.add_argument("--iscc-path", default="", help="Inno Setup iscc.exe 路径（默认从 PATH 查找）")
    parser.add_argument("--skip-installer", action="store_true", help="跳过安装包制作")
    return parser.parse_args()


def build_enterprise_dir(args: argparse.Namespace) -> Path:
    """在 staging 区域生成企业配置目录，返回 enterprise/ 路径"""
    staging = Path(tempfile.mkdtemp(prefix="enterprise_build_"))
    target = staging / "enterprise"
    target.mkdir(parents=True, exist_ok=True)

    short_name = args.customer_short_name or args.customer_name
    banner_text = f"{short_name}专用版"

    profile = {
        "enabled": True,
        "customer_name": args.customer_name,
        "customer_short_name": short_name,
        "product_name": args.product_name,
        "edition_name": args.edition_name,
        "banner_text": banner_text,
        "logo_path": "logo.png" if args.logo else None,
        "default_terms": [],
    }

    (target / "profile.json").write_text(
        json.dumps(profile, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if args.logo:
        logo_src = Path(args.logo)
        if logo_src.exists():
            shutil.copy2(logo_src, target / "logo.png")
            print(f"  Logo: {logo_src.name} -> enterprise/logo.png")
        else:
            print(f"  [WARN] Logo 文件不存在: {logo_src}", file=sys.stderr)

    if args.terms:
        terms_src = Path(args.terms)
        if terms_src.exists():
            shutil.copy2(terms_src, target / "terms.csv")
            print(f"  词库: {terms_src.name} -> enterprise/terms.csv")
        else:
            print(f"  [WARN] 词库文件不存在: {terms_src}", file=sys.stderr)
    else:
        _write_default_terms_csv(target, args.customer_name, short_name)
        print(f"  词库: 生成默认词库（{args.customer_name} / {short_name}）")

    print(f"  企业配置目录: {target}")
    return target


def _write_default_terms_csv(target: Path, full_name: str, short_name: str) -> None:
    """没有提供词库时，生成仅含企业全称和简称的默认词库"""
    path = target / "terms.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["value", "entity", "category", "note"])
        writer.writerow([full_name, "ORGANIZATION", "企业名称", "企业全称"])
        if short_name and short_name != full_name:
            writer.writerow([short_name, "ORGANIZATION", "企业简称", "企业简称"])


def run_pyinstaller(spec_path: Path) -> Path:
    """运行 PyInstaller，返回输出目录路径"""
    print(f"\n[2/5] 运行 PyInstaller...")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", str(spec_path)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        sys.exit(1)
    output_dir = DEFAULT_OUTPUT / SPEC_FILE.stem
    if not output_dir.exists():
        print("  [ERROR] PyInstaller 构建失败，输出目录未生成", file=sys.stderr)
        sys.exit(1)
    print(f"  PyInstaller 构建完成: {output_dir}")
    return output_dir


def inject_enterprise_config(app_dir: Path, enterprise_src: Path) -> None:
    """将企业配置目录拷贝到 PyInstaller 输出目录中"""
    print(f"\n[3/5] 注入企业配置...")
    target = app_dir / "enterprise"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(enterprise_src, target)
    print(f"  企业配置已注入: {target}")
    _print_enterprise_summary(enterprise_src)


def _print_enterprise_summary(enterprise_dir: Path) -> None:
    profile_path = enterprise_dir / "profile.json"
    if not profile_path.exists():
        return
    profile = json.loads(profile_path.read_text(encoding="utf-8"))
    term_count = _count_terms(enterprise_dir)
    print(f"  客户: {profile.get('customer_name', '?')}")
    print(f"  产品: {profile.get('product_name', '?')} - {profile.get('edition_name', '?')}")
    print(f"  词库: {term_count} 条")
    print(f"  Logo: {'有' if (enterprise_dir / 'logo.png').exists() else '无'}")


def _count_terms(enterprise_dir: Path) -> int:
    count = 0
    for pattern in ("terms.csv", "terms.txt"):
        path = enterprise_dir / pattern
        if path.exists():
            count += sum(1 for _ in path.read_text(encoding="utf-8-sig").splitlines() if _.strip())
    profile_path = enterprise_dir / "profile.json"
    if profile_path.exists():
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
        count += len(profile.get("default_terms", []))
    return count


def find_iscc(args: argparse.Namespace) -> str:
    if args.iscc_path:
        return args.iscc_path
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\iscc.exe",
        r"C:\Program Files\Inno Setup 6\iscc.exe",
        r"C:\Program Files (x86)\Inno Setup\iscc.exe",
        r"C:\Program Files\Inno Setup\iscc.exe",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return candidate
    which = shutil.which("iscc")
    if which:
        return which
    return ""


def _ensure_installer_dir() -> Path:
    installer_dir = PROJECT_ROOT / "installer"
    installer_dir.mkdir(exist_ok=True)
    return installer_dir


def build_inno_setup(app_dir: Path, args: argparse.Namespace) -> Path | None:
    """生成安装包，返回安装包路径"""
    iscc = find_iscc(args)
    if not iscc:
        print("\n[4/5] 跳过安装包：未找到 iscc.exe（Inno Setup）")
        print("  可安装 Inno Setup 6 或将 iscc.exe 所在目录加入 PATH")
        return None

    print(f"\n[4/5] 生成安装包 (Inno Setup)...")
    short_name = args.customer_short_name or args.customer_name
    timestamp = datetime.now().strftime("%Y%m%d")
    output_filename = f"企业资料脱敏工具-{short_name}-定制安装包-{timestamp}"

    installer_dir = _ensure_installer_dir()
    iss_path = installer_dir / "setup.iss"

    iss_content = _generate_iss_script(
        app_dir=app_dir,
        customer_name=short_name,
        product_name=args.product_name,
        output_dir=Path(args.output_dir),
        output_filename=output_filename,
    )
    iss_path.write_text(iss_content, encoding="utf-8-sig")
    print(f"  Inno Setup 脚本: {iss_path}")

    result = subprocess.run(
        [iscc, str(iss_path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"  [WARN] Inno Setup 编译失败:\n{result.stderr}", file=sys.stderr)
        return None

    installer_path = Path(args.output_dir) / f"{output_filename}.exe"
    if installer_path.exists():
        print(f"  安装包生成成功: {installer_path}")
        return installer_path

    print(f"  [WARN] 安装包未在预期位置找到", file=sys.stderr)
    return None


def _generate_iss_script(
    app_dir: Path,
    customer_name: str,
    product_name: str,
    output_dir: Path,
    output_filename: str,
) -> str:
    app_dir_abs = app_dir.resolve()
    app_name = f"{product_name} - {customer_name}专用版"

    lines = [
        f"; Inno Setup 脚本 - 由 build_enterprise.py 自动生成",
        f'#define MyAppName "{app_name}"',
        f'#define MyAppVersion "2.0.0"',
        f'#define MyAppPublisher "艺林万象（北京）科技有限公司"',
        f'#define MyAppURL ""',
        f'#define MyAppExeName "本地资料脱敏工具.exe"',
        f"",
        f"[Setup]",
        f"AppId={{{{F8B7A3D2-4E19-4C6A-9B5C-1D2E3F4A5B6C}}}}",
        f"AppName={{#MyAppName}}",
        f"AppVersion={{#MyAppVersion}}",
        f"AppPublisher={{#MyAppPublisher}}",
        f"DefaultDirName={{{{autopf}}}}\\{app_name}",
        f"DisableProgramGroupPage=yes",
        f"PrivilegesRequiredOverridesAllowed=dialog",
        f"OutputDir={output_dir}",
        f"OutputBaseFilename={output_filename}",
        f"Compression=lzma",
        f"SolidCompression=yes",
        f"WizardStyle=modern",
        f"SetupIconFile={PROJECT_ROOT}\\assets\\app_icon.ico",
        f"UninstallDisplayIcon={{{{app}}}}\\{{#MyAppExeName}}",
        f"DisableWelcomePage=no",
        f"",
        f"[Languages]",
        f'Name: "chinesesimplified"; MessagesFile: "compiler:Languages\\ChineseSimplified.isl"',
        f"",
        f"[Tasks]",
        f'Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: checkedonce',
        f"",
        f"[Files]",
        f'Source: "{app_dir_abs}\\*"; DestDir: "{{app}}"; Flags: ignoreversion recursesubdirs createallsubdirs',
        f"",
        f"[Icons]",
        f'Name: "{{autoprograms}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"',
        f'Name: "{{autodesktop}}\\{{#MyAppName}}"; Filename: "{{app}}\\{{#MyAppExeName}}"; Tasks: desktopicon',
        f"",
        f"[Run]",
        f'Filename: "{{app}}\\{{#MyAppExeName}}"; Description: "运行 {{#MyAppName}}"; Flags: postinstall nowait skipifsilent unchecked',
        f"",
        f"[UninstallRun]",
        f"",
    ]
    return "\n".join(lines)


def cleanup(staging_dir: Path) -> None:
    """清理 staging 目录"""
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
        print(f"\n[5/5] 清理临时文件")


def main() -> None:
    args = parse_args()
    print("=" * 60)
    print("  企业定制版构建工具")
    print(f"  客户: {args.customer_name}")
    print("=" * 60)

    short_name = args.customer_short_name or args.customer_name
    print(f"\n[1/5] 生成企业配置（{short_name}）...")
    enterprise_dir = build_enterprise_dir(args)

    pyinstaller_output = run_pyinstaller(SPEC_FILE)

    inject_enterprise_config(pyinstaller_output, enterprise_dir)

    if not args.skip_installer:
        build_inno_setup(pyinstaller_output, args)
    else:
        print(f"\n[4/5] 跳过安装包（--skip-installer）")

    cleanup(enterprise_dir.parent)

    print(f"\n{'=' * 60}")
    print(f"  构建完成！")
    print(f"  输出: {pyinstaller_output}")
    installer = Path(args.output_dir)
    print(f"  安装包目录: {installer}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
