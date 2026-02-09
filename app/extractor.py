import httpx
from bs4 import BeautifulSoup
import re
import logging

logger = logging.getLogger(__name__)


def normalize_key(key: str) -> str:
    """Normaliza a chave para um formato padrão em minúsculas e sem acentos."""
    key = key.lower().strip()
    # Remove acentos
    key = key.replace('ç', 'c').replace('ã', 'a').replace('õ', 'o')
    key = key.replace('á', 'a').replace('é', 'e').replace('í', 'i').replace('ó', 'o').replace('ú', 'u')
    key = key.replace('â', 'a').replace('ê', 'e').replace('î', 'i').replace('ô', 'o').replace('û', 'u')
    return key


def parse_resultado_pre(text: str) -> dict:
    """
    Parseia o conteúdo de uma tag <pre> que contém os dados de um resultado.
    Formato esperado:
        NOME: Joao Silva
        CPF: 000.188.958-32
        SEXO: M - Masculino
        NASCIMENTO: 05/11/1943
        IDADE: 82 anos
    """
    result = {}
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for line in lines:
        if ':' in line:
            parts = line.split(':', 1)
            if len(parts) == 2:
                key = normalize_key(parts[0].strip())
                value = parts[1].strip()
                if key and value:
                    result[key] = value
    
    return result


async def extract_telegraph_data(url: str):
    """
    Extrai dados de uma página do Telegraph e retorna uma lista de resultados formatados.
    
    A estrutura HTML do Telegraph é:
    <article class="tl_article_content">
        <p><strong>RESULTADO 1</strong></p>
        <pre>NOME: valor
CPF: valor...</pre>
        <p><strong>RESULTADO 2</strong></p>
        <pre>...</pre>
    </article>
    """
    if not url or not ("telegra.ph" in url or "telegraph" in url):
        return []

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                logger.error(f"Erro ao acessar Telegraph: {response.status_code}")
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Procura pelo article com a classe tl_article_content
            article = soup.find('article', class_='tl_article_content')
            if not article:
                # Tenta encontrar qualquer article
                article = soup.find('article')
            
            if not article:
                logger.warning("Não foi possível encontrar o conteúdo do artigo no Telegraph")
                return []

            resultados = []
            current_result = None
            
            # Itera sobre todos os elementos filhos do article
            for element in article.children:
                if element.name == 'p':
                    # Verifica se é um cabeçalho de resultado
                    text = element.get_text(strip=True)
                    # Padrão: "RESULTADO 1", "RESULTADO 2", etc.
                    if re.search(r'RESULTADO\s*\d+', text, re.IGNORECASE):
                        # Salva o resultado anterior se existir
                        if current_result and current_result.get('dados'):
                            resultados.append(current_result)
                        
                        # Extrai o número do resultado
                        match = re.search(r'RESULTADO\s*(\d+)', text, re.IGNORECASE)
                        numero = int(match.group(1)) if match else len(resultados) + 1
                        
                        current_result = {
                            "numero": numero,
                            "dados": {},
                            "sections": {"dados": {}}
                        }
                
                elif element.name == 'pre' and current_result is not None:
                    # Extrai os dados do bloco <pre>
                    pre_text = element.get_text(separator='\n')
                    dados = parse_resultado_pre(pre_text)
                    if dados:
                        current_result["dados"] = dados
                        current_result["sections"]["dados"] = dados
            
            # Adiciona o último resultado
            if current_result and current_result.get('dados'):
                resultados.append(current_result)
            
            logger.info(f"Extraídos {len(resultados)} resultados do Telegraph")
            return resultados

    except httpx.TimeoutException:
        logger.error("Timeout ao acessar o Telegraph")
        return []
    except Exception as e:
        logger.error(f"Erro na extração do Telegraph: {e}", exc_info=True)
        return []


async def extract_telegraph_data_v2(url: str):
    """
    Versão alternativa que usa uma abordagem mais robusta para extrair dados.
    Procura por padrões de resultado no HTML completo.
    """
    if not url or not ("telegra.ph" in url or "telegraph" in url):
        return []

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = await client.get(url, headers=headers)
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Tenta encontrar o article
            article = soup.find('article', class_='tl_article_content') or soup.find('article')
            
            if not article:
                return []
            
            # Obtém todo o texto e procura por padrões
            html_content = str(article)
            
            # Padrão para encontrar blocos de resultado
            # <p><strong>RESULTADO N</strong></p><pre>...</pre>
            pattern = r'<p>\s*<strong>\s*RESULTADO\s*(\d+)\s*</strong>\s*</p>\s*<pre[^>]*>(.*?)</pre>'
            matches = re.findall(pattern, html_content, re.IGNORECASE | re.DOTALL)
            
            resultados = []
            for match in matches:
                numero = int(match[0])
                pre_content = match[1]
                
                # Limpa o conteúdo do pre (remove tags HTML se houver)
                pre_soup = BeautifulSoup(pre_content, 'html.parser')
                pre_text = pre_soup.get_text(separator='\n')
                
                dados = parse_resultado_pre(pre_text)
                if dados:
                    resultados.append({
                        "numero": numero,
                        "dados": dados,
                        "sections": {"dados": dados}
                    })
            
            # Se não encontrou com regex, tenta com BeautifulSoup
            if not resultados:
                strong_tags = article.find_all('strong')
                for strong in strong_tags:
                    text = strong.get_text(strip=True)
                    if re.search(r'RESULTADO\s*\d+', text, re.IGNORECASE):
                        match = re.search(r'RESULTADO\s*(\d+)', text, re.IGNORECASE)
                        numero = int(match.group(1)) if match else len(resultados) + 1
                        
                        # Procura o próximo elemento <pre> irmão
                        next_sibling = strong.find_parent('p')
                        if next_sibling:
                            pre_tag = next_sibling.find_next_sibling('pre')
                            if pre_tag:
                                dados = parse_resultado_pre(pre_tag.get_text(separator='\n'))
                                if dados:
                                    resultados.append({
                                        "numero": numero,
                                        "dados": dados,
                                        "sections": {"dados": dados}
                                    })
            
            return resultados

    except Exception as e:
        logger.error(f"Erro na extração v2 do Telegraph: {e}")
        return []


if __name__ == "__main__":
    import asyncio
    import json
    
    # Teste com o arquivo local
    async def test():
        print("Testando extrator com arquivo local...")
        
        # Lê o arquivo HTML local para teste
        try:
            with open('telegraph_page.html', 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            article = soup.find('article', class_='tl_article_content')
            
            if article:
                resultados = []
                current_result = None
                
                for element in article.children:
                    if element.name == 'p':
                        text = element.get_text(strip=True)
                        if re.search(r'RESULTADO\s*\d+', text, re.IGNORECASE):
                            if current_result and current_result.get('dados'):
                                resultados.append(current_result)
                            
                            match = re.search(r'RESULTADO\s*(\d+)', text, re.IGNORECASE)
                            numero = int(match.group(1)) if match else len(resultados) + 1
                            
                            current_result = {
                                "numero": numero,
                                "dados": {},
                                "sections": {"dados": {}}
                            }
                    
                    elif element.name == 'pre' and current_result is not None:
                        pre_text = element.get_text(separator='\n')
                        dados = parse_resultado_pre(pre_text)
                        if dados:
                            current_result["dados"] = dados
                            current_result["sections"]["dados"] = dados
                
                if current_result and current_result.get('dados'):
                    resultados.append(current_result)
                
                print(f"\nEncontrados {len(resultados)} resultados:")
                print(json.dumps(resultados[:3], indent=2, ensure_ascii=False))
            else:
                print("Article não encontrado no arquivo local")
                
        except Exception as e:
            print(f"Erro no teste: {e}")
            import traceback
            traceback.print_exc()
    
    asyncio.run(test())
