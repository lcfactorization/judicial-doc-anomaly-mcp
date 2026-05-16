"""Tests for adversarial module"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from judicial_lint_mcp.adversarial import (
    ROLE_NAMES_CN,
    AdversarialResult,
    AdversarialReviewer,
    CrossExaminationResult,
)
from judicial_lint_mcp.config import AdversarialConfig


@pytest.fixture
def adversarial_config():
    return AdversarialConfig(
        roles=[
            "plaintiff_agent",
            "defendant_agent",
            "appellate_judge",
            "legal_scholar",
            "public_supervisor",
        ],
        enable_devils_advocate=True,
        enable_multi_role=True,
        enable_cross_examination=True,
    )


@pytest.fixture
def minimal_config():
    return AdversarialConfig(
        roles=["plaintiff_agent", "defendant_agent"],
        enable_devils_advocate=True,
        enable_multi_role=False,
        enable_cross_examination=False,
    )


@pytest.fixture
def mock_llm_caller():
    caller = MagicMock()
    caller.acall = AsyncMock(return_value=("", {"total_tokens": 0}))
    return caller


MOCK_ADVERSARIAL_OUTPUT = """
## Devil's Advocate 反向审查

异常点1：举证责任分配错误
Q1替代解释：法院可能认为原告证据不足以证明劳动关系
Q1有替代解释：是
Q2无意图仍成立：是，即使无主观意图，客观上仍导致举证责任倒置
Q3反证：被告提交的项目合作协议可作为反证
Q3有反证：是
✅ 异常成立

异常点2：证据采信双标
Q1替代解释：工作证照片确实可能无法确认真实性
Q1有替代解释：是
Q2无意图仍成立：否，可能只是审查标准不同
Q3反证：无
Q3有反证：否
⚠️ 异常存疑

异常点3：笔迹鉴定申请被拒
Q1替代解释：法院可能认为鉴定无必要
Q1有替代解释：否
Q2无意图仍成立：是
Q3反证：无
Q3有反证：否
✅ 异常成立

## 多角色对抗审查

原告代理人：该判决存在明显偏袒，应重点审查举证责任分配和证据采信标准
被告代理人：判决认定事实清楚，适用法律正确
上诉审查法官：程序存在瑕疵，笔迹鉴定申请被拒需进一步审查
法学学者：劳动关系认定标准适用存在争议
公众监督者：司法公正性存疑

## 交叉质证

举证责任分配错误：原告代理人、上诉审查法官、法学学者确认，被告代理人否认
证据采信双标：原告代理人确认，被告代理人否认
笔迹鉴定申请被拒：原告代理人、上诉审查法官确认
"""


class TestAdversarialDevilsAdvocate:

    def test_parse_devils_advocate_established(
        self, mock_llm_caller, adversarial_config
    ):
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        results = reviewer._parse_devils_advocate(MOCK_ADVERSARIAL_OUTPUT)
        assert len(results) >= 1
        established = [r for r in results if r.conclusion == "成立"]
        assert len(established) >= 1

    def test_parse_devils_advocate_doubtful(self, mock_llm_caller, adversarial_config):
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        results = reviewer._parse_devils_advocate(MOCK_ADVERSARIAL_OUTPUT)
        doubtful = [r for r in results if r.conclusion == "存疑"]
        assert len(doubtful) >= 1

    def test_parse_devils_advocate_empty(self, mock_llm_caller, adversarial_config):
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        results = reviewer._parse_devils_advocate("没有任何异常标记")
        assert len(results) >= 1
        assert results[0].conclusion in ("", "存疑")

    def test_parse_devils_advocate_rejected(self, mock_llm_caller, adversarial_config):
        output = "异常点1：测试异常\n❌ 异常不成立"
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        results = reviewer._parse_devils_advocate(output)
        rejected = [r for r in results if r.conclusion == "不成立"]
        assert len(rejected) >= 1


class TestAdversarialRoleReviews:

    def test_parse_role_reviews(self, mock_llm_caller, adversarial_config):
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        reviews = reviewer._parse_role_reviews(MOCK_ADVERSARIAL_OUTPUT)
        assert len(reviews) >= 1
        role_keys = [r.role for r in reviews]
        assert any(k in role_keys for k in adversarial_config.roles)

    def test_parse_role_reviews_minimal(self, mock_llm_caller, minimal_config):
        reviewer = AdversarialReviewer(mock_llm_caller, minimal_config)
        reviews = reviewer._parse_role_reviews("简单输出")
        assert len(reviews) >= 1

    def test_role_names_cn_mapping(self):
        assert "plaintiff_agent" in ROLE_NAMES_CN
        assert "defendant_agent" in ROLE_NAMES_CN
        assert "appellate_judge" in ROLE_NAMES_CN
        assert "legal_scholar" in ROLE_NAMES_CN
        assert "public_supervisor" in ROLE_NAMES_CN
        assert ROLE_NAMES_CN["plaintiff_agent"] == "原告代理人"


class TestAdversarialRun:

    @pytest.mark.asyncio
    async def test_run_full(self, mock_llm_caller, adversarial_config):
        mock_llm_caller.acall = AsyncMock(
            return_value=(MOCK_ADVERSARIAL_OUTPUT, {"total_tokens": 500})
        )
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        result = await reviewer.run("测试异常文本")

        assert isinstance(result, AdversarialResult)
        assert len(result.devils_advocate_results) >= 1
        assert result.raw_llm_output == MOCK_ADVERSARIAL_OUTPUT

    @pytest.mark.asyncio
    async def test_run_minimal(self, mock_llm_caller, minimal_config):
        mock_llm_caller.acall = AsyncMock(
            return_value=("简单输出", {"total_tokens": 100})
        )
        reviewer = AdversarialReviewer(mock_llm_caller, minimal_config)
        result = await reviewer.run("测试异常文本")

        assert isinstance(result, AdversarialResult)
        assert len(result.devils_advocate_results) >= 1
        assert len(result.role_reviews) == 0
        assert len(result.cross_examinations) == 0

    @pytest.mark.asyncio
    async def test_run_devils_advocate_disabled(self, mock_llm_caller):
        config = AdversarialConfig(
            roles=[],
            enable_devils_advocate=False,
            enable_multi_role=False,
            enable_cross_examination=False,
        )
        reviewer = AdversarialReviewer(mock_llm_caller, config)
        result = await reviewer.run("测试")

        assert isinstance(result, AdversarialResult)
        assert len(result.devils_advocate_results) == 0

    @pytest.mark.asyncio
    async def test_cross_examination_with_confirmed_points(
        self, mock_llm_caller, adversarial_config
    ):
        mock_llm_caller.acall = AsyncMock(
            return_value=(MOCK_ADVERSARIAL_OUTPUT, {"total_tokens": 500})
        )
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        result = await reviewer.run("测试异常文本")

        if result.cross_examinations:
            for ce in result.cross_examinations:
                assert isinstance(ce, CrossExaminationResult)
                assert ce.risk_point != ""
                assert isinstance(ce.confirming_roles, list)

    @pytest.mark.asyncio
    async def test_high_risk_points(self, mock_llm_caller, adversarial_config):
        mock_llm_caller.acall = AsyncMock(
            return_value=(MOCK_ADVERSARIAL_OUTPUT, {"total_tokens": 500})
        )
        reviewer = AdversarialReviewer(mock_llm_caller, adversarial_config)
        result = await reviewer.run("测试异常文本")

        if result.high_risk_points:
            for hp in result.high_risk_points:
                assert "risk_level" in hp
                assert "point" in hp
                assert hp["risk_level"] in ("高", "中")


class TestAdversarialConfig:

    def test_default_config(self):
        config = AdversarialConfig()
        assert config.enable_devils_advocate is True
        assert config.enable_multi_role is True
        assert config.enable_cross_examination is True
        assert len(config.roles) == 5

    def test_custom_config(self):
        config = AdversarialConfig(
            roles=["plaintiff_agent"],
            enable_devils_advocate=True,
            enable_multi_role=False,
            enable_cross_examination=False,
        )
        assert len(config.roles) == 1
        assert config.enable_multi_role is False
