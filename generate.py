#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Samba News - Daily Newsletter Generator
Fetches RSS feeds, generates content with Claude, sends HTML preview via Gmail.
"""

import feedparser
import json
import os
import smtplib
import sys
from datetime import datetime
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from anthropic import Anthropic

ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER = os.environ["GMAIL_USER"]
GMAIL_APP_PASSWORD = os.environ["GMAIL_APP_PASSWORD"]
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]

client = Anthropic(api_key=ANTHROPIC_API_KEY)

RSS_FEEDS = {
    "eua": [
        "https://feeds.npr.org/1001/rss.xml",
        "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml",
        "https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml",
        "https://rss.cnn.com/rss/edition.rss",
        "https://time.com/feed/",
        "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    ],
    "brasil": [
        "https://g1.globo.com/rss/g1/",
        "https://www.bbc.com/portuguese/rss.xml",
        "https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.rss",
        "https://www.cnnbrasil.com.br/feed/",
        "https://www.metropoles.com/feed/",
        "https://www.correiobraziliense.com.br/rss/ultimas-noticias/feed.xml",
        "https://g1.globo.com/rss/g1/politica/",
        "https://www.cnnbrasil.com.br/politica/feed/",
    ],
    "economia": [
        "https://feeds.bbci.co.uk/news/business/rss.xml",
        "https://www.infomoney.com.br/feed/",
        "https://feeds.reuters.com/reuters/businessNews",
        "https://www.cnbc.com/id/10000664/device/rss/rss.html",
        "https://feeds.businessinsider.com/custom/all",
    ],
    "tech": [
        "https://www.theverge.com/rss/index.xml",
        "https://techcrunch.com/feed/",
        "https://feeds.wired.com/wired/index",
        "https://feeds.arstechnica.com/arstechnica/index",
        "https://feeds.businessinsider.com/custom/tech",
    ],
    "copa": [
        "https://ge.globo.com/rss/ge/futebol/copa-do-mundo/",
        "https://www.uol.com.br/esporte/futebol/copa-do-mundo/rss.xml",
        "https://feeds.bbci.co.uk/sport/football/rss.xml",
        "https://www.espn.com.br/rss/futebol/copa-do-mundo/noticias",
    ],
}

MONTHS_PT = {
    1: "JANEIRO", 2: "FEVEREIRO", 3: "MARCO", 4: "ABRIL",
    5: "MAIO", 6: "JUNHO", 7: "JULHO", 8: "AGOSTO",
    9: "SETEMBRO", 10: "OUTUBRO", 11: "NOVEMBRO", 12: "DEZEMBRO",
}
WEEKDAYS_PT = {
    0: "SEGUNDA-FEIRA", 1: "TERCA-FEIRA", 2: "QUARTA-FEIRA",
    3: "QUINTA-FEIRA", 4: "SEXTA-FEIRA", 5: "SABADO", 6: "DOMINGO",
}


def date_str_pt(dt):
    return f"{WEEKDAYS_PT[dt.weekday()]}, {dt.day} DE {MONTHS_PT[dt.month]} DE {dt.year}"


def fetch_feeds(section):
    items = []
    for url in RSS_FEEDS.get(section, []):
        try:
            feed = feedparser.parse(url, request_headers={"User-Agent": "SambaNewsBot/1.0"})
            for entry in feed.entries[:5]:
                summary = entry.get("summary", entry.get("description", ""))
                import re
                summary = re.sub(r"<[^>]+>", " ", summary)[:600]
                items.append({
                    "title": entry.get("title", ""),
                    "summary": summary.strip(),
                    "source": feed.feed.get("title", url),
                    "url": entry.get("link", ""),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"[WARN] Feed error ({url}): {e}", file=sys.stderr)
    return items[:12]


def generate_content(feeds):
    eua_json = json.dumps(feeds["eua"], ensure_ascii=False, indent=2)
    brasil_json = json.dumps(feeds["brasil"], ensure_ascii=False, indent=2)
    economia_json = json.dumps(feeds["economia"], ensure_ascii=False, indent=2)
    tech_json = json.dumps(feeds["tech"], ensure_ascii=False, indent=2)
    copa_json = json.dumps(feeds["copa"], ensure_ascii=False, indent=2)

    prompt = (
        "Voce e o editor da Samba News, newsletter diaria em portugues para brasileiros nos EUA.\n\n"
        "Tom: leve, claro, apartidario e humano. Cada secao tem DUAS noticias principais completas "
        "(para o editor escolher a melhor) e 3 links rapidos compartilhados ao final.\n\n"
        "CRITERIOS DE SELECAO POR SECAO:\n\n"
        "EUA - Escolha as 2 noticias de MAIOR REPERCUSSAO NACIONAL nos EUA naquele dia. "
        "As que qualquer americano estaria comentando. Se houver empate, prefira as que tiverem "
        "impacto direto no bolso ou no cotidiano de quem mora la. Nao precisa ser sobre imigracao "
        "- pode ser politica, economia americana, saude, clima, seguranca ou sociedade. "
        "Os 3 links rapidos devem cobrir temas DIFERENTES das duas noticias principais.\n\n"
        "BRASIL - Escolha as 2 noticias que quem esta longe do Brasil mais sentiria falta de saber. "
        "As que familiares e amigos no Brasil estariam comentando naquele dia. "
        "Os 3 links rapidos devem cobrir temas DIFERENTES das duas noticias principais. "
        "OBRIGATORIO: um dos 3 links rapidos deve ser sobre politica brasileira ou eleicoes 2026 - "
        "sempre, sem excecao.\n\n"
        "ECONOMIA - Escolha as 2 noticias de maior impacto pratico para quem tem vida financeira "
        "nos dois paises: ganha em dolar, manda dinheiro pro Brasil ou tem investimentos nos dois lados. "
        "Os 3 links rapidos devem cobrir outros temas economicos, sem repetir os assuntos principais.\n\n"
        "TECH E NEGOCIOS - Escolha as 2 noticias que mais impactam o futuro do trabalho e da vida digital. "
        "Prioridade: IA, Big Tech (Apple, Google, Meta, Amazon, Microsoft, OpenAI), carreira em tech e "
        "regulacao de tecnologia. Os 3 links rapidos devem cobrir outros temas de tech ou negocios, "
        "sem repetir os assuntos principais.\n\n"
        "COPA DO MUNDO 2026 - Secao especial de futebol. Estamos no periodo da Copa do Mundo 2026 "
        "(11 junho a 19 julho), realizada nos EUA, Canada e Mexico. Use as noticias de copa disponiveis abaixo. Gere:\n"
        "- scores: lista dos jogos mais recentes com placar (use os dados dos feeds ou, se nao houver, informe 'placar nao disponivel nos feeds').\n"
        "- headlines: exatamente 3 noticias rapidas sobre a Copa - resultados, curiosidades, polemicas, "
        "desempenho do Brasil. Frases curtas, tom animado, maximo 2 linhas cada.\n\n"
        "REGRA GERAL: os 3 links de cada secao nunca repetem os temas das duas noticias principais. "
        "Use URLs reais dos feeds fornecidos, nunca invente URLs.\n\n"
        "NOTICIAS DISPONIVEIS:\n\n"
        "=== EUA ===\n" + eua_json + "\n\n"
        "=== BRASIL ===\n" + brasil_json + "\n\n"
        "=== ECONOMIA ===\n" + economia_json + "\n\n"
        "=== TECH E NEGOCIOS ===\n" + tech_json + "\n\n"
        "=== COPA DO MUNDO ===\n" + copa_json + "\n\n"
        "INSTRUCOES DE ESCRITA - ESTILO THE NEWS:\n\n"
        "Escreva como um amigo bem informado explicando a noticia num cafe. Nao como jornalista. "
        "Nao como professor. Como alguem que entende do assunto e quer que voce entenda tambem, em 5 minutos.\n\n"
        "REGRAS DE OURO:\n"
        "- Frases curtas. Maximo 20 palavras por frase. Se ficou longa, corta em duas.\n"
        "- Sem jargao. 'Banco Central elevou a Selic' vira 'os juros subiram de novo'.\n"
        "- Use numeros concretos. Nao 'muitas empresas'. Use '47 empresas' ou '1 em cada 3'.\n"
        "- Fale direto com o leitor. Use 'voce' sempre que fizer sentido.\n"
        "- Sem linguagem de jornal formal. Nada de 'segundo informou', 'conforme declarou'.\n"
        "- Humor leve quando couber. Nunca forcado.\n\n"
        "ESTRUTURA DE CADA PARAGRAFO:\n"
        "- paragraph_1 (gancho): comece com uma pergunta, dado surpreendente ou situacao relatable. "
        "Apresente O QUE aconteceu de forma clara e direta. 2-3 frases.\n"
        "- paragraph_2 (contexto): explique POR QUE isso aconteceu ou qual e o cenario por tras. 2-3 frases.\n"
        "- paragraph_3 (e agora?): o que vem por ai. Consequencias praticas, proximos passos, "
        "o que o leitor deve ficar de olho. Termine sempre com uma perspectiva para frente. 2-3 frases.\n"
        "- why_it_matters: seja PESSOAL e ESPECIFICO para brasileiros nos EUA. 2-3 frases diretas.\n\n"
        "TITULO DA NOTICIA (story_title): curto, direto, sem verbo no infinitivo.\n\n"
        "TITULO MOTIVACIONAL: filosofico, provocativo, com no maximo 4 palavras.\n"
        "FRASE MOTIVACIONAL: complementa o titulo. Tom reflexivo, nao autoajuda. 1-2 linhas em italico.\n\n"
        "Retorne SOMENTE JSON valido, sem markdown, sem explicacao.\n\n"
        "ESTRUTURA JSON OBRIGATORIA (use exatamente estes nomes de campos):\n\n"
        '{\n'
        '  "motivational_title": "titulo filosofico curto (2-4 palavras)",\n'
        '  "motivational_phrase": "frase inspiradora relacionada ao titulo (1-2 linhas)",\n'
        '  "copa": {\n'
        '    "scores": [\n'
        '      {"match": "Brasil x Marrocos", "score": "2-0", "status": "Encerrado"},\n'
        '      {"match": "EUA x Paraguai", "score": "1-1", "status": "Encerrado"}\n'
        '    ],\n'
        '    "headlines": [\n'
        '      "Texto da noticia rapida 1 sobre a Copa.",\n'
        '      "Texto da noticia rapida 2 sobre a Copa.",\n'
        '      "Texto da noticia rapida 3 sobre a Copa."\n'
        '    ]\n'
        '  },\n'
        '  "sections": [\n'
        '    {\n'
        '      "id": "eua",\n'
        '      "label": "ESTADOS UNIDOS",\n'
        '      "emoji": "\U0001F1FA\U0001F1F8",\n'
        '      "stories": [\n'
        '        {\n'
        '          "story_title": "titulo da noticia A em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        },\n'
        '        {\n'
        '          "story_title": "titulo da noticia B em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        }\n'
        '      ],\n'
        '      "leia_mais": [\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."}\n'
        '      ]\n'
        '    },\n'
        '    {\n'
        '      "id": "brasil",\n'
        '      "label": "BRASIL",\n'
        '      "emoji": "\U0001F1E7\U0001F1F7",\n'
        '      "stories": [\n'
        '        {\n'
        '          "story_title": "titulo da noticia A em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        },\n'
        '        {\n'
        '          "story_title": "titulo da noticia B em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        }\n'
        '      ],\n'
        '      "leia_mais": [\n'
        '        {"title": "titulo sobre politica brasileira ou eleicoes 2026", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."}\n'
        '      ]\n'
        '    },\n'
        '    {\n'
        '      "id": "economia",\n'
        '      "label": "ECONOMIA",\n'
        '      "emoji": "\U0001F4B5",\n'
        '      "stories": [\n'
        '        {\n'
        '          "story_title": "titulo da noticia A em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        },\n'
        '        {\n'
        '          "story_title": "titulo da noticia B em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        }\n'
        '      ],\n'
        '      "leia_mais": [\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."}\n'
        '      ]\n'
        '    },\n'
        '    {\n'
        '      "id": "tech",\n'
        '      "label": "TECH E NEGOCIOS",\n'
        '      "emoji": "\U0001F4BB",\n'
        '      "stories": [\n'
        '        {\n'
        '          "story_title": "titulo da noticia A em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        },\n'
        '        {\n'
        '          "story_title": "titulo da noticia B em portugues",\n'
        '          "source": "Nome da Fonte",\n'
        '          "paragraph_1": "fatos principais",\n'
        '          "paragraph_2": "contexto",\n'
        '          "paragraph_3": "o que pode acontecer a seguir",\n'
        '          "why_it_matters": "relevancia para brasileiros nos EUA"\n'
        '        }\n'
        '      ],\n'
        '      "leia_mais": [\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."},\n'
        '        {"title": "titulo", "source": "Fonte", "url": "https://..."}\n'
        '      ]\n'
        '    }\n'
        '  ]\n'
        '}'
    )

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        messages=[{"role": "user", "content": prompt}],
    )

    raw = message.content[0].text.strip()
    if "```" in raw:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        raw = raw[start:end]
    return json.loads(raw)


def render_story(story, option_label, option_color):
    pin = "\U0001F4CD"
    return (
        '<div style="border:2px solid ' + option_color + ';border-radius:6px;padding:24px 28px;margin-bottom:20px;">'
        '<div style="margin-bottom:14px;">'
        '<span style="background-color:' + option_color + ';color:#ffffff;padding:4px 12px;font-size:11px;font-weight:700;letter-spacing:1.5px;border-radius:3px;display:inline-block;">' + option_label + '</span>'
        '</div>'
        '<h2 style="font-family:Inter,Arial,sans-serif;font-size:21px;font-weight:700;color:#1a5c2a;margin:0 0 6px 0;line-height:1.3;">' + story["story_title"] + '</h2>'
        '<p style="font-size:12px;color:#9ca3af;margin:0 0 18px 0;font-style:italic;">via ' + story["source"] + '</p>'
        '<p style="font-family:Inter,Arial,sans-serif;font-size:16px;color:#1f2937;line-height:1.75;margin:0 0 14px 0;">' + story["paragraph_1"] + '</p>'
        '<p style="font-family:Inter,Arial,sans-serif;font-size:16px;color:#1f2937;line-height:1.75;margin:0 0 14px 0;">' + story["paragraph_2"] + '</p>'
        '<p style="font-family:Inter,Arial,sans-serif;font-size:16px;color:#1f2937;line-height:1.75;margin:0 0 20px 0;">' + story["paragraph_3"] + '</p>'
        '<div style="background-color:#fdf8ee;border-left:4px solid #f5c842;padding:16px 20px;margin:0;border-radius:0 4px 4px 0;">'
        '<p style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#374151;margin:0 0 8px 0;">' + pin + ' POR QUE ISSO IMPORTA PRA VOC\u00CA</p>'
        '<p style="font-size:15px;color:#374151;margin:0;line-height:1.65;">' + story["why_it_matters"] + '</p>'
        '</div>'
        '</div>'
    )


def render_copa_html(copa):
    scores_html = ""
    for s in copa.get("scores", []):
        status_color = "#16a34a" if "Encerrado" in s.get("status", "") else "#d97706"
        scores_html += (
            '<div style="display:inline-block;background:#fff;border:1px solid #e5e7eb;border-radius:6px;'
            'padding:10px 18px;margin:4px;text-align:center;min-width:160px;">'
            '<p style="font-size:12px;color:#6b7280;margin:0 0 4px 0;font-family:Inter,Arial,sans-serif;">' + s.get("match", "") + '</p>'
            '<p style="font-size:20px;font-weight:700;color:#1a1a1a;margin:0 0 4px 0;font-family:Inter,Arial,sans-serif;">' + s.get("score", "") + '</p>'
            '<span style="font-size:10px;font-weight:700;letter-spacing:1px;color:' + status_color + ';">' + s.get("status", "") + '</span>'
            '</div>'
        )

    headlines_html = ""
    for h in copa.get("headlines", []):
        headlines_html += (
            '<div style="border-top:1px solid #e5e7eb;padding:12px 0;">'
            '<p style="font-size:15px;color:#1f2937;margin:0;line-height:1.6;font-family:Inter,Arial,sans-serif;">'
            '\u26bd ' + h +
            '</p></div>'
        )

    return (
        '<div style="margin-bottom:48px;">'
        '<div style="margin-bottom:16px;">'
        '<span style="background-color:#f5c842;padding:5px 14px;font-size:11px;font-weight:700;'
        'letter-spacing:1.5px;color:#1a1a1a;border-radius:3px;display:inline-block;">'
        '\u26bd COPA DO MUNDO 2026</span>'
        '</div>'
        '<div style="background-color:#f0fdf4;border:1px solid #bbf7d0;border-radius:6px;'
        'padding:20px 24px;margin-bottom:20px;text-align:center;">'
        '<p style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#15803d;'
        'margin:0 0 14px 0;font-family:Inter,Arial,sans-serif;">PLACARES RECENTES</p>'
        '<div style="text-align:center;">' + scores_html + '</div>'
        '</div>'
        '<div style="padding:0 4px;">' + headlines_html + '</div>'
        '</div>'
        '<hr style="border:none;border-top:2px solid #f3f4f6;margin:0 0 40px 0;">'
    )


def render_html(content, dt):
    date_label = date_str_pt(dt)

    copa_html = render_copa_html(content.get("copa", {}))

    # Summary shows BOTH story titles per section so editor can choose which to use in Beehiiv
    summary_items = ""
    for s in content["sections"]:
        stories = s.get("stories", [])
        title_a = stories[0]["story_title"] if len(stories) > 0 else ""
        title_b = stories[1]["story_title"] if len(stories) > 1 else ""
        summary_items += (
            '<li style="margin-bottom:16px;">'
            '<span style="font-size:13px;font-weight:700;letter-spacing:1px;color:#1a5c2a;">' + s["emoji"] + ' ' + s["label"] + '</span><br>'
            '<span style="display:inline-block;margin-top:6px;font-size:14px;color:#1f2937;">'
            '<span style="background-color:#1a5c2a;color:#fff;font-size:10px;font-weight:700;'
            'padding:2px 7px;border-radius:3px;letter-spacing:1px;vertical-align:middle;">OP1</span>'
            '&nbsp;' + title_a +
            '</span><br>'
            '<span style="display:inline-block;margin-top:4px;font-size:14px;color:#4b5563;">'
            '<span style="background-color:#374151;color:#fff;font-size:10px;font-weight:700;'
            'padding:2px 7px;border-radius:3px;letter-spacing:1px;vertical-align:middle;">OP2</span>'
            '&nbsp;' + title_b +
            '</span>'
            '</li>'
        )

    sections_html = ""
    for s in content["sections"]:
        stories = s.get("stories", [])

        story_a_html = render_story(stories[0], "OPC\u00C3O 1", "#1a5c2a") if len(stories) > 0 else ""
        story_b_html = render_story(stories[1], "OPC\u00C3O 2", "#374151") if len(stories) > 1 else ""

        leia_mais_html = ""
        for item in s.get("leia_mais", []):
            leia_mais_html += (
                '<div style="border-top:1px solid #e5e7eb;padding:10px 0;">'
                '<a href="' + item["url"] + '" style="color:#374151;text-decoration:none;font-size:14px;">'
                '&#8212;&nbsp;' + item["title"] +
                ' <span style="color:#9ca3af;font-size:13px;">(' + item["source"] + ')</span>'
                '</a></div>'
            )

        sections_html += (
            '<div style="margin-bottom:48px;">'
            '<div style="margin-bottom:16px;">'
            '<span style="background-color:#f5c842;padding:5px 14px;font-size:11px;font-weight:700;'
            'letter-spacing:1.5px;color:#1a1a1a;border-radius:3px;display:inline-block;">'
            + s["emoji"] + ' ' + s["label"] +
            '</span></div>'
            + story_a_html +
            '<div style="text-align:center;padding:4px 0;margin-bottom:4px;">'
            '<span style="font-size:11px;font-weight:700;letter-spacing:2px;color:#9ca3af;">- OU -</span>'
            '</div>'
            + story_b_html +
            '<div style="margin-top:24px;">'
            '<p style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#9ca3af;margin:0 0 2px 0;">LEIA MAIS</p>'
            + leia_mais_html +
            '</div></div>'
            '<hr style="border:none;border-top:2px solid #f3f4f6;margin:0 0 40px 0;">'
        )

    wa_text = (
        "https://wa.me/?text=Todo+dia+gasto+5+minutos+lendo+a+Samba+News+e+j%C3%A1+sei+tudo+que"
        "+t%C3%A1+acontecendo+nos+EUA+e+no+Brasil.+Feita+por+quem+tamb%C3%A9m+vive+essa+vida+"
        "aqui.+%C3%89+gr%C3%A1tis%2C+s%C3%B3+entrar+no+link+e+se+inscrever%3A+"
        "sambanews.beehiiv.com%2Fsubscribe"
    )

    return (
        "<!DOCTYPE html>\n"
        '<html lang="pt-BR">\n'
        "<head>\n"
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1.0">\n'
        '<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">\n'
        "<title>Samba News</title>\n"
        "</head>\n"
        '<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Inter,Arial,sans-serif;">\n'
        '<div style="max-width:680px;margin:0 auto;background-color:#ffffff;">\n\n'

        # Header
        '<div style="padding:32px 40px 24px 40px;text-align:center;border-bottom:1px solid #e5e7eb;">'
        '<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">'
        '<table cellpadding="0" cellspacing="0"><tr>'
        '<td style="vertical-align:middle;padding-right:10px;">'
        '<div style="width:36px;height:36px;border-radius:50%;background-color:#28a745;text-align:center;line-height:36px;">'
        '<div style="width:13px;height:13px;border-radius:50%;background-color:#f5c842;display:inline-block;vertical-align:middle;margin-top:-1px;"></div>'
        '</div></td>'
        '<td style="vertical-align:middle;">'
        '<span style="font-size:22px;font-weight:700;color:#1a237e;font-family:Inter,Arial,sans-serif;letter-spacing:-0.5px;">samba news</span>'
        '</td></tr></table></td></tr></table>'
        '<p style="font-size:11px;letter-spacing:2px;color:#9ca3af;margin:12px 0 0 0;font-weight:500;font-family:Inter,Arial,sans-serif;">' + date_label + '</p>'
        '</div>\n\n'

        # Motivational
        '<div style="padding:32px 40px 28px 40px;text-align:center;border-bottom:3px solid #f5c842;">'
        '<h1 style="font-family:Inter,Arial,sans-serif;font-size:26px;font-weight:700;color:#1a1a1a;margin:0 0 12px 0;">' + content["motivational_title"] + '</h1>'
        '<p style="font-style:italic;color:#4b5563;font-size:16px;line-height:1.6;margin:0;font-family:Inter,Arial,sans-serif;">' + content["motivational_phrase"] + '</p>'
        '</div>\n\n'

        # Summary
        '<div style="background-color:#f9f7f2;padding:24px 40px;border-bottom:1px solid #e5e7eb;">'
        '<p style="font-size:11px;font-weight:700;letter-spacing:2px;color:#9ca3af;margin:0 0 16px 0;font-family:Inter,Arial,sans-serif;">NA EDI\u00c7\u00c3O DE HOJE</p>'
        '<ul style="list-style:none;padding:0;margin:0;font-family:Inter,Arial,sans-serif;">' + summary_items + '</ul>'
        '</div>\n\n'

        # Editorial banner
        '<div style="background-color:#fffbeb;border:1px solid #f5c842;padding:14px 40px;text-align:center;">'
        '<p style="font-size:12px;color:#92400e;margin:0;font-family:Inter,Arial,sans-serif;font-weight:600;">'
        '\u270f\ufe0f PR\u00c9VIA EDITORIAL - Cada se\u00e7\u00e3o tem 2 op\u00e7\u00f5es. Escolha a que preferir para publicar no Beehiiv.'
        '</p></div>\n\n'

        # Sections + Copa
        '<div style="padding:40px 40px 16px 40px;">' + sections_html + copa_html + '</div>\n\n'

        # Share block
        '<div style="background-color:#f9f7f2;border-top:3px solid #f5c842;padding:32px 40px;text-align:center;">'
        '<p style="font-size:11px;font-weight:700;letter-spacing:2px;color:#9ca3af;margin:0 0 12px 0;font-family:Inter,Arial,sans-serif;">COMPARTILHE COM QUEM PRECISA</p>'
        '<p style="font-size:16px;color:#1f2937;line-height:1.7;margin:0 0 24px 0;font-family:Inter,Arial,sans-serif;">'
        'Tem algum brasileiro no seu grupo que ainda n\u00e3o l\u00ea a Samba News?<br>Manda pra ele. \u00c9 gr\u00e1tis e leva 5 minutos por dia.'
        '</p>'
        '<a href="' + wa_text + '" '
        'style="display:inline-block;background-color:#25D366;color:#ffffff;font-family:Inter,Arial,sans-serif;'
        'font-size:15px;font-weight:700;padding:14px 28px;border-radius:6px;text-decoration:none;letter-spacing:0.5px;">'
        '\U0001F4F2 Compartilhar no WhatsApp'
        '</a>'
        '</div>\n\n'

        # Footer
        '<div style="background-color:#1a1a1a;padding:28px 40px;text-align:center;">'
        '<div style="width:28px;height:28px;border-radius:50%;background-color:#28a745;text-align:center;line-height:28px;display:inline-block;margin-bottom:10px;">'
        '<div style="width:10px;height:10px;border-radius:50%;background-color:#f5c842;display:inline-block;vertical-align:middle;margin-top:-1px;"></div>'
        '</div>'
        '<p style="color:#9ca3af;font-size:13px;margin:0 0 6px 0;font-family:Inter,Arial,sans-serif;">Feito com amor para brasileiros nos EUA</p>'
        '<p style="color:#6b7280;font-size:12px;margin:0;font-family:Inter,Arial,sans-serif;">Voc\u00ea recebe este email porque se inscreveu na Samba News.</p>'
        '</div>\n\n'

        '</div>\n</body>\n</html>'
    )


def send_email(html, subject):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL

    msg.attach(MIMEText(html, "html", "utf-8"))

    attachment = MIMEBase("text", "html")
    attachment.set_payload(html.encode("utf-8"))
    encoders.encode_base64(attachment)
    attachment.add_header(
        "Content-Disposition", "attachment",
        filename=f"samba-news-{datetime.now().strftime('%Y-%m-%d')}.html"
    )
    msg.attach(attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
    print(f"Email enviado para {RECIPIENT_EMAIL}")


def main():
    now = datetime.now()
    print(f"Samba News - {date_str_pt(now)}")

    feeds = {
        "eua": fetch_feeds("eua"),
        "brasil": fetch_feeds("brasil"),
        "economia": fetch_feeds("economia"),
        "tech": fetch_feeds("tech"),
        "copa": fetch_feeds("copa"),
    }

    content = generate_content(feeds)
    html = render_html(content, now)
    subject = f"Samba News - {now.strftime('%d/%m/%Y')} [PREVIEW]"
    send_email(html, subject)
    print("Concluido!")


if __name__ == "__main__":
    main()
