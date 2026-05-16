"""Real end-to-end test with DeepSeek API for A1-A8 classification and 16-dimension scoring."""
import asyncio
import os
import sys

from dotenv import load_dotenv
load_dotenv()

from judicial_lint_mcp.server import scan_dimension, dry_run, benchmark_compare


async def main():
    case_dir = "tests/fixtures/sample_case"

    print("=" * 60)
    print("Step 1: dry_run 预览")
    print("=" * 60)
    preview = await dry_run(case_dir)
    print(preview[:1500])

    print("\n" + "=" * 60)
    print("Step 2: scan_dimension 维度2(证据采信) - 测试A1-A8映射")
    print("=" * 60)
    result = await scan_dimension(case_dir, 2)
    print(result[:3000])

    has_a_code = any(code in result for code in ["A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8"])
    has_beneficiary = "获益" in result or "被告" in result or "原告" in result
    has_reverse = "反向" in result or "校验" in result

    print("\n" + "=" * 60)
    print("Step 3: benchmark_compare 测试")
    print("=" * 60)
    bench_result = benchmark_compare("A1,A4", None)
    print(bench_result[:1000])

    print("\n" + "=" * 60)
    print("验证结果")
    print("=" * 60)
    checks = [
        ("A系列分类映射", has_a_code),
        ("指向获益方", has_beneficiary),
        ("反向校验", has_reverse),
        ("基准对比", "BM-001" in bench_result),
    ]
    all_pass = True
    for name, ok in checks:
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  {status} {name}")

    if all_pass:
        print("\n✅ 真实端到端测试通过")
    else:
        print("\n❌ 存在测试失败")


if __name__ == "__main__":
    asyncio.run(main())
