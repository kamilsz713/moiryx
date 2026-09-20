"""Eagerly validated public Agent facade."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from pathlib import Path

from pydantic import BaseModel

from moiryx.agent_spec import AgentSpec, load_agent_spec
from moiryx.config import CapabilityOverrides, RuntimeConfig, load_config
from moiryx.errors import ConfigurationError, ProviderCapabilityError
from moiryx.generation import merge_generation_options
from moiryx.model_registry import ModelRegistry, ResolvedModel
from moiryx.models import GenerationOptions, ProviderCapabilities, ToolDefinition
from moiryx.observability import RunObserver
from moiryx.providers import ProviderAdapter, ProviderRegistry
from moiryx.redaction import collect_secret_values
from moiryx.runtime import execute_structured_agent, execute_text_agent
from moiryx.tools import GLOBAL_TOOL_REGISTRY, build_builtin_tool


@dataclass(frozen=True, slots=True)
class _PreparedAgent:
    spec: AgentSpec
    model: ResolvedModel
    provider: ProviderAdapter
    tools: tuple[ToolDefinition, ...]
    capabilities: ProviderCapabilities
    generation: GenerationOptions
    runtime: RuntimeConfig
    observer: RunObserver


def _import_tool_modules(module_names: list[str]) -> None:
    for module_name in module_names:
        try:
            import_module(module_name)
        except Exception as error:
            raise ConfigurationError(
                f"Could not import tool module '{module_name}' ({type(error).__name__})"
            ) from error


def _effective_capabilities(
    adapter: ProviderCapabilities,
    overrides: CapabilityOverrides,
) -> ProviderCapabilities:
    return ProviderCapabilities(
        tool_calling=(
            adapter.tool_calling
            if overrides.tool_calling is None
            else overrides.tool_calling
        ),
        native_structured_output=(
            adapter.native_structured_output
            if overrides.native_structured_output is None
            else overrides.native_structured_output
        ),
        parallel_tool_calls=(
            adapter.parallel_tool_calls
            if overrides.parallel_tool_calls is None
            else overrides.parallel_tool_calls
        ),
    )


def _validate_capabilities(
    *,
    spec: AgentSpec,
    model: ResolvedModel,
    capabilities: ProviderCapabilities,
) -> None:
    if spec.tool_names and not capabilities.tool_calling:
        raise ProviderCapabilityError(
            "Agent tools require provider tool-calling capability",
            agent_name=spec.name,
            model_alias=model.alias,
            provider_name=model.provider,
            model_id=model.model,
        )

    if spec.output_model is None:
        return
    supports_output = capabilities.tool_calling or (
        not spec.tool_names and capabilities.native_structured_output
    )
    if not supports_output:
        raise ProviderCapabilityError(
            "Structured output requires tool calling or guaranteed native "
            "structured output without user tools",
            agent_name=spec.name,
            model_alias=model.alias,
            provider_name=model.provider,
            model_id=model.model,
        )


class Agent:
    """An immutable, eagerly resolved agent definition ready for execution."""

    __slots__ = ("_prepared", "_provider_registry")

    def __init__(self, agent_file: str | Path) -> None:
        config = load_config()
        _import_tool_modules(config.tool_modules)
        spec = load_agent_spec(
            agent_file,
            default_max_steps=config.runtime.default_max_steps,
        )
        model = ModelRegistry(config).resolve(spec.model_alias)
        tools = tuple(
            build_builtin_tool(name, config.runtime)
            or GLOBAL_TOOL_REGISTRY.resolve(name)
            for name in spec.tool_names
        )

        provider_registry = ProviderRegistry(config)
        provider = provider_registry.resolve(model.provider)
        try:
            adapter_capabilities = provider.capabilities
        except (AttributeError, TypeError) as error:
            raise ConfigurationError(
                "Provider adapter does not expose valid capabilities",
                provider_name=model.provider,
            ) from error
        if not isinstance(adapter_capabilities, ProviderCapabilities):
            raise ConfigurationError(
                "Provider adapter returned invalid capabilities",
                provider_name=model.provider,
            )
        provider_config = config.providers[model.provider]
        capabilities = _effective_capabilities(
            adapter_capabilities,
            provider_config.capabilities,
        )
        _validate_capabilities(
            spec=spec,
            model=model,
            capabilities=capabilities,
        )
        generation = merge_generation_options(
            config.runtime.generation,
            model.generation,
            spec.generation,
        )

        self._provider_registry = provider_registry
        self._prepared = _PreparedAgent(
            spec=spec,
            model=model,
            provider=provider,
            tools=tools,
            capabilities=capabilities,
            generation=generation,
            runtime=config.runtime,
            observer=RunObserver(
                config.logging,
                secrets=collect_secret_values(config),
            ),
        )

    async def __call__(self, prompt: str) -> str | BaseModel:
        """Execute one isolated run of this eagerly prepared agent."""
        if self._prepared.spec.output_model is not None:
            return await execute_structured_agent(
                provider=self._prepared.provider,
                spec=self._prepared.spec,
                model=self._prepared.model,
                tools=self._prepared.tools,
                capabilities=self._prepared.capabilities,
                generation=self._prepared.generation,
                runtime=self._prepared.runtime,
                prompt=prompt,
                observer=self._prepared.observer,
            )
        return await execute_text_agent(
            provider=self._prepared.provider,
            spec=self._prepared.spec,
            model=self._prepared.model,
            tools=self._prepared.tools,
            generation=self._prepared.generation,
            runtime=self._prepared.runtime,
            prompt=prompt,
            observer=self._prepared.observer,
        )

    async def aclose(self) -> None:
        """Release the provider client when this agent is no longer needed."""
        await self._provider_registry.close()

    async def __aenter__(self) -> Agent:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.aclose()


__all__ = ["Agent"]
