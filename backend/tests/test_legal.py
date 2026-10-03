import pytest
from httpx import AsyncClient


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("path", "title", "required_text"),
    [
        (
            "/privacidade",
            "Política de Privacidade — FlashPost",
            "segredo é criptografado",
        ),
        (
            "/termosdeuso",
            "Termos de Serviço — FlashPost",
            "não é afiliado, endossado ou administrado pela Meta",
        ),
        (
            "/deletar",
            "Instruções de exclusão de dados — FlashPost",
            "Exclusão de dados — FlashPost",
        ),
    ],
)
async def test_public_meta_information_pages_are_real_html(
    client: AsyncClient,
    path: str,
    title: str,
    required_text: str,
) -> None:
    response = await client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert f"<title>{title}</title>" in response.text
    assert "FlashPost" in response.text
    assert required_text in response.text
    assert "<h1>" in response.text
    assert "mailto:lucassantosdz111@gmail.com" in response.text
