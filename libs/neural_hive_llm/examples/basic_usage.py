"""
Exemplo básico de uso de neural_hive_llm.

Demonstra os principais recursos da biblioteca.
"""

import asyncio
import os


async def main():
    """Executa exemplos de uso."""
    from neural_hive_llm import LLMClient, LLMProvider

    # Exemplo 1: Provider Local (Ollama)
    print("=" * 60)
    print("Exemplo 1: Provider Local (Ollama)")
    print("=" * 60)

    local_client = LLMClient(
        provider=LLMProvider.LOCAL,
        base_url="http://localhost:11434",
        model="llama2",
    )

    try:
        await local_client.start()
        print("✓ Cliente local inicializado\n")

        # Gerar resposta simples
        response = await local_client.generate(
            prompt="O que é uma API? Responda em português.",
            max_tokens=100,
        )

        print(f"Resposta: {response.text}")
        print(f"Tokens: {response.total_tokens}")
        print(f"Latência: {response.latency_ms:.2f}ms\n")

    except Exception as e:
        print(f"✗ Erro: {e}")
        print("Certifique-se que Ollama está rodando em localhost:11434\n")
    finally:
        await local_client.stop()

    # Exemplo 2: Provider OpenAI (com API key)
    print("=" * 60)
    print("Exemplo 2: Provider OpenAI")
    print("=" * 60)

    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        openai_client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key=api_key,
            model="gpt-3.5-turbo",
        )

        try:
            await openai_client.start()
            print("✓ Cliente OpenAI inicializado\n")

            # Gerar resposta com system prompt
            response = await openai_client.generate(
                prompt="Explique microserviços em uma frase.",
                system_prompt="Você é um arquiteto de software experiente.",
                temperature=0.7,
                max_tokens=100,
            )

            print(f"Resposta: {response.text}")
            print(f"Tokens: {response.total_tokens}")
            print(f"Custo estimado: ${response.estimated_cost_usd:.6f}\n")

        finally:
            await openai_client.stop()
    else:
        print("✗ OPENAI_API_KEY não configurada\n")

    # Exemplo 3: Streaming
    print("=" * 60)
    print("Exemplo 3: Streaming")
    print("=" * 60)

    if api_key:
        streaming_client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key=api_key,
            model="gpt-3.5-turbo",
        )

        try:
            await streaming_client.start()
            print("✓ Cliente para streaming inicializado\n")
            print("Resposta: ", end="")

            async for chunk in streaming_client.generate_stream(
                prompt="Conte até 5 em português.",
                temperature=0.0,
            ):
                print(chunk.text, end="", flush=True)

            print("\n")

        finally:
            await streaming_client.stop()
    else:
        print("✗ OPENAI_API_KEY não configurada\n")

    # Exemplo 4: Batch
    print("=" * 60)
    print("Exemplo 4: Geração em Batch")
    print("=" * 60)

    if api_key:
        batch_client = LLMClient(
            provider=LLMProvider.OPENAI,
            api_key=api_key,
            model="gpt-3.5-turbo",
        )

        try:
            await batch_client.start()
            print("✓ Cliente para batch inicializado\n")

            prompts = [
                "O que é Python? (uma frase)",
                "O que é FastAPI? (uma frase)",
                "O que é Docker? (uma frase)",
            ]

            responses = await batch_client.generate_batch(
                prompts=prompts, temperature=0.5, max_tokens=50
            )

            for i, response in enumerate(responses, 1):
                print(f"{i}. {response.text[:80]}...")

            print()

        finally:
            await batch_client.stop()
    else:
        print("✗ OPENAI_API_KEY não configurada\n")

    # Exemplo 5: Context Manager
    print("=" * 60)
    print("Exemplo 5: Context Manager")
    print("=" * 60)

    if api_key:
        async with LLMClient(
            provider=LLMProvider.OPENAI, api_key=api_key, model="gpt-3.5-turbo"
        ) as client:
            response = await client.generate("Diga olá em português!")
            print(f"Resposta: {response.text}\n")
    else:
        print("✗ OPENAI_API_KEY não configurada\n")

    # Exemplo 6: Tratamento de Erros
    print("=" * 60)
    print("Exemplo 6: Tratamento de Erros")
    print("=" * 60)

    from neural_hive_llm.exceptions import (
        LLMError,
        LLMRateLimitError,
        LLMTimeoutError,
    )

    error_client = LLMClient(
        provider=LLMProvider.OPENAI,
        api_key="sk-invalid-key-12345",  # Key inválida
        model="gpt-3.5-turbo",
    )

    try:
        await error_client.start()
        response = await error_client.generate("Teste")
    except LLMRateLimitError:
        print("✗ Rate limit excedido")
    except LLMTimeoutError:
        print("✗ Timeout da requisição")
    except LLMError as e:
        print(f"✗ Erro LLM: {type(e).__name__}")
    except Exception as e:
        print(f"✗ Erro genérico: {type(e).__name__}")
    finally:
        try:
            await error_client.stop()
        except Exception:
            pass

    print("\n" + "=" * 60)
    print("Exemplos concluídos!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
