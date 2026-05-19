#!/usr/bin/env python3
"""
Samba News — Daily Newsletter Generator
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
}

MONTHS_PT = {1:"JANEIRO",2:"FEVEREIRO",3:"MARÇO",4:"ABRIL",5:"MAIO",6:"JUNHO",
             7:"JULHO",8:"AGOSTO",9:"SETEMBRO",10:"OUTUBRO",11:"NOVEMBRO",12:"DEZEMBRO"}
WEEKDAYS_PT = {0:"SEGUNDA-FEIRA",1:"TERÇA-FEIRA",2:"QUARTA-FEIRA",
               3:"QUINTA-FEIRA",4:"SEXTA-FEIRA",5:"SÁBADO",6:"DOMINGO"}

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
    prompt = f"""Você é o editor da Samba News, newsletter diária em português para brasileiros nos EUA.

Tom: leve, claro, apartidário e humano. Cada seção tem DUAS notícias principais completas (para o editor escolher a melhor) e 3 links rápidos compartilhados ao final.

CRITÉRIOS DE SELEÇÃO POR SEÇÃO:

EUA — Escolha as 2 notícias de MAIOR REPERCUSSÃO NACIONAL nos EUA naquele dia. As que qualquer americano estaria comentando. Se houver empate, prefira as que tiverem impacto direto no bolso ou no cotidiano de quem mora lá. Não precisa ser sobre imigração — pode ser política, economia americana, saúde, clima, segurança ou sociedade. Os 3 links rápidos devem cobrir temas DIFERENTES das duas notícias principais.

BRASIL — Escolha as 2 notícias que quem está longe do Brasil mais sentiria falta de saber. As que familiares e amigos no Brasil estariam comentando naquele dia. Os 3 links rápidos devem cobrir temas DIFERENTES das duas notícias principais.

ECONOMIA — Escolha as 2 notícias de maior impacto prático para quem tem vida financeira nos dois países: ganha em dólar, manda dinheiro pro Brasil ou tem investimentos nos dois lados. Os 3 links rápidos devem cobrir outros temas econômicos, sem repetir os assuntos principais.

TECH E NEGOCIOS — Escolha as 2 notícias que mais impactam o futuro do trabalho e da vida digital. Prioridade: IA, Big Tech (Apple, Google, Meta, Amazon, Microsoft, OpenAI), carreira em tech e regulação de tecnologia. Os 3 links rápidos devem cobrir outros temas de tech ou negócios, sem repetir os assuntos principais.

REGRA GERAL: os 3 links de cada seção nunca repetem os temas das duas notícias principais. Use URLs reais dos feeds fornecidos, nunca invente URLs.

NOTICIAS DISPONIVEIS:

=== EUA ===
{json.dumps(feeds["eua"], ensure_ascii=False, indent=2)}

=== BRASIL ===
{json.dumps(feeds["brasil"], ensure_ascii=False, indent=2)}

=== ECONOMIA ===
{json.dumps(feeds["economia"], ensure_ascii=False, indent=2)}

=== TECH E NEGOCIOS ===
{json.dumps(feeds["tech"], ensure_ascii=False, indent=2)}

INSTRUCOES DE ESCRITA — ESTILO THE NEWS:

Escreva como um amigo bem informado explicando a notícia num café. Não como jornalista. Não como professor. Como alguém que entende do assunto e quer que você entenda também, em 5 minutos.

REGRAS DE OURO:
- Frases curtas. Máximo 20 palavras por frase. Se ficou longa, corta em duas.
- Sem jargão. "Banco Central elevou a Selic" vira "os juros subiram de novo".
- Use números concretos. Não "muitas empresas". Use "47 empresas" ou "1 em cada 3".
- Fale direto com o leitor. Use "você" sempre que fizer sentido.
- Sem linguagem de jornal formal. Nada de "segundo informou", "conforme declarou", "de acordo com fontes".
- Humor leve quando couber. Nunca forçado.

ESTRUTURA DE CADA PARÁGRAFO:
- paragraph_1 (gancho): comece com uma pergunta, dado surpreendente ou situação relatable. Apresente O QUE aconteceu de forma clara e direta. 2-3 frases.
- paragraph_2 (contexto): explique POR QUE isso aconteceu ou qual é o cenário por trás. 2-3 frases.
- paragraph_3 (e agora?): o que vem por aí. Consequências práticas, próximos passos, o que o leitor deve ficar de olho. Termine sempre com uma perspectiva para frente. 2-3 frases.
- why_it_matters: seja PESSOAL e ESPECÍFICO para brasileiros nos EUA. 2-3 frases diretas.

TITULO DA NOTICIA (story_title): curto, direto, sem verbo no infinitivo.

TITULO MOTIVACIONAL: filosófico, provocativo, com no máximo 4 palavras.
FRASE MOTIVACIONAL: complementa o título. Tom reflexivo, não autoajuda. 1-2 linhas em itálico.

Retorne SOMENTE JSON válido, sem markdown, sem explicação.

ESTRUTURA JSON OBRIGATORIA (use exatamente estes nomes de campos):

{{
  "motivational_title": "título filosófico curto (2-4 palavras)",
  "motivational_phrase": "frase inspiradora relacionada ao título (1-2 linhas)",
  "sections": [
    {{
      "id": "eua",
      "label": "ESTADOS UNIDOS",
      "emoji": "🇺🇸",
      "stories": [
        {{
          "story_title": "título da notícia A em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }},
        {{
          "story_title": "título da notícia B em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }}
      ],
      "leia_mais": [
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}}
      ]
    }},
    {{
      "id": "brasil",
      "label": "BRASIL",
      "emoji": "🇧🇷",
      "stories": [
        {{
          "story_title": "título da notícia A em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }},
        {{
          "story_title": "título da notícia B em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }}
      ],
      "leia_mais": [
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}}
      ]
    }},
    {{
      "id": "economia",
      "label": "ECONOMIA",
      "emoji": "💵",
      "stories": [
        {{
          "story_title": "título da notícia A em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }},
        {{
          "story_title": "título da notícia B em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }}
      ],
      "leia_mais": [
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}}
      ]
    }},
    {{
      "id": "tech",
      "label": "TECH E NEGÓCIOS",
      "emoji": "💻",
      "stories": [
        {{
          "story_title": "título da notícia A em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }},
        {{
          "story_title": "título da notícia B em português",
          "source": "Nome da Fonte",
          "paragraph_1": "fatos principais",
          "paragraph_2": "contexto",
          "paragraph_3": "o que pode acontecer a seguir",
          "why_it_matters": "relevância para brasileiros nos EUA"
        }}
      ],
      "leia_mais": [
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}},
        {{"title": "título", "source": "Fonte", "url": "https://..."}}
      ]
    }}
  ]
}}"""

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
    """Renders a single story block with an option label."""
    return f"""
<div style="border:2px solid {option_color};border-radius:6px;padding:24px 28px;margin-bottom:20px;">
  <div style="margin-bottom:14px;">
    <span style="background-color:{option_color};color:#ffffff;padding:4px 12px;font-size:11px;font-weight:700;letter-spacing:1.5px;border-radius:3px;display:inline-block;">{option_label}</span>
  </div>
  <h2 style="font-family:Inter,Arial,sans-serif;font-size:21px;font-weight:700;color:#1a5c2a;margin:0 0 6px 0;line-height:1.3;">{story["story_title"]}</h2>
  <p style="font-size:12px;color:#9ca3af;margin:0 0 18px 0;font-style:italic;">via {story["source"]}</p>
  <p style="font-family:Inter,Arial,sans-serif;font-size:16px;color:#1f2937;line-height:1.75;margin:0 0 14px 0;">{story["paragraph_1"]}</p>
  <p style="font-family:Inter,Arial,sans-serif;font-size:16px;color:#1f2937;line-height:1.75;margin:0 0 14px 0;">{story["paragraph_2"]}</p>
  <p style="font-family:Inter,Arial,sans-serif;font-size:16px;color:#1f2937;line-height:1.75;margin:0 0 20px 0;">{story["paragraph_3"]}</p>
  <div style="background-color:#fdf8ee;border-left:4px solid #f5c842;padding:16px 20px;margin:0;border-radius:0 4px 4px 0;">
    <p style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#374151;margin:0 0 8px 0;">📍 POR QUE ISSO IMPORTA PRA VOCÊ</p>
    <p style="font-size:15px;color:#374151;margin:0;line-height:1.65;">{story["why_it_matters"]}</p>
  </div>
</div>"""


def render_html(content, dt):
    date_label = date_str_pt(dt)

    # Summary uses only the first story of each section
    summary_items = "".join(
        f'<li style="margin-bottom:10px;font-size:15px;color:#1f2937;">{s["emoji"]}&nbsp;{s["stories"][0]["story_title"]}</li>'
        for s in content["sections"]
    )

    sections_html = ""
    for s in content["sections"]:
        stories = s.get("stories", [])

        story_a_html = render_story(stories[0], "OPÇÃO 1", "#1a5c2a") if len(stories) > 0 else ""
        story_b_html = render_story(stories[1], "OPÇÃO 2", "#374151") if len(stories) > 1 else ""

        leia_mais_html = "".join(
            f'<div style="border-top:1px solid #e5e7eb;padding:10px 0;"><a href="{item["url"]}" style="color:#374151;text-decoration:none;font-size:14px;">&#8212;&nbsp;{item["title"]} <span style="color:#9ca3af;font-size:13px;">({item["source"]})</span></a></div>'
            for item in s.get("leia_mais", [])
        )

        sections_html += f"""
<div style="margin-bottom:48px;">
  <div style="margin-bottom:16px;">
    <span style="background-color:#f5c842;padding:5px 14px;font-size:11px;font-weight:700;letter-spacing:1.5px;color:#1a1a1a;border-radius:3px;display:inline-block;">{s["emoji"]} {s["label"]}</span>
  </div>

  {story_a_html}

  <div style="text-align:center;padding:4px 0 4px 0;margin-bottom:4px;">
    <span style="font-size:11px;font-weight:700;letter-spacing:2px;color:#9ca3af;">— OU —</span>
  </div>

  {story_b_html}

  <div style="margin-top:24px;">
    <p style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#9ca3af;margin:0 0 2px 0;">LEIA MAIS</p>
    {leia_mais_html}
  </div>
</div>

<hr style="border:none;border-top:2px solid #f3f4f6;margin:0 0 40px 0;">"""

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<title>Samba News</title>
</head>
<body style="margin:0;padding:0;background-color:#f3f4f6;font-family:Inter,Arial,sans-serif;">
<div style="max-width:680px;margin:0 auto;background-color:#ffffff;">

  <div style="padding:32px 40px 24px 40px;text-align:center;border-bottom:1px solid #e5e7eb;">
    <table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
    <table cellpadding="0" cellspacing="0"><tr>
      <td style="vertical-align:middle;padding-right:10px;">
        <div style="width:36px;height:36px;border-radius:50%;background-color:#28a745;text-align:center;line-height:36px;">
          <div style="width:13px;height:13px;border-radius:50%;background-color:#f5c842;display:inline-block;vertical-align:middle;margin-top:-1px;"></div>
        </div>
      </td>
      <td style="vertical-align:middle;">
        <span style="font-size:22px;font-weight:700;color:#1a237e;font-family:Inter,Arial,sans-serif;letter-spacing:-0.5px;">samba news</span>
      </td>
    </tr></table>
    </td></tr></table>
    <p style="font-size:11px;letter-spacing:2px;color:#9ca3af;margin:12px 0 0 0;font-weight:500;font-family:Inter,Arial,sans-serif;">{date_label}</p>
  </div>

  <div style="padding:32px 40px 28px 40px;text-align:center;border-bottom:3px solid #f5c842;">
    <h1 style="font-family:Inter,Arial,sans-serif;font-size:26px;font-weight:700;color:#1a1a1a;margin:0 0 12px 0;">{content["motivational_title"]}</h1>
    <p style="font-style:italic;color:#4b5563;font-size:16px;line-height:1.6;margin:0;font-family:Inter,Arial,sans-serif;">{content["motivational_phrase"]}</p>
  </div>

  <div style="background-color:#f9f7f2;padding:24px 40px;border-bottom:1px solid #e5e7eb;">
    <p style="font-size:11px;font-weight:700;letter-spacing:2px;color:#9ca3af;margin:0 0 16px 0;font-family:Inter,Arial,sans-serif;">NA EDIÇÃO DE HOJE</p>
    <ul style="list-style:none;padding:0;margin:0;font-family:Inter,Arial,sans-serif;">{summary_items}</ul>
  </div>

  <div style="background-color:#fffbeb;border:1px solid #f5c842;padding:14px 40px;text-align:center;">
    <p style="font-size:12px;color:#92400e;margin:0;font-family:Inter,Arial,sans-serif;font-weight:600;">
      ✏️ PRÉVIA EDITORIAL — Cada seção tem 2 opções. Escolha a que preferir para publicar no Beehiiv.
    </p>
  </div>

  <div style="padding:40px 40px 16px 40px;">{sections_html}</div>

  <div style="background-color:#1a1a1a;padding:28px 40px;text-align:center;">
    <div style="width:28px;height:28px;border-radius:50%;background-color:#28a745;text-align:center;line-height:28px;display:inline-block;margin-bottom:10px;">
      <div style="width:10px;height:10px;border-radius:50%;background-color:#f5c842;display:inline-block;vertical-align:middle;margin-top:-1px;"></div>
    </div>
    <p style="color:#9ca3af;font-size:13px;margin:0 0 6px 0;font-family:Inter,Arial,sans-serif;">Feito com amor para brasileiros nos EUA</p>
    <p style="color:#6b7280;font-size:12px;margin:0;font-family:Inter,Arial,sans-serif;">Você recebe este email porque se inscreveu na Samba News.</p>
  </div>

</div>
</body>
</html>"""


def send_email(html, subject):
    msg = MIMEMultipart("mixed")
    msg["Subject"] = subject
    msg["From"] = GMAIL_USER
    msg["To"] = RECIPIENT_EMAIL

    msg.attach(MIMEText(html, "html", "utf-8"))

    attachment = MIMEBase("text", "html")
    attachment.set_payload(html.encode("utf-8"))
    encoders.encode_base64(attachment)
    attachment.add_header("Content-Disposition", "attachment",
                          filename=f"samba-news-{datetime.now().strftime('%Y-%m-%d')}.html")
    msg.attach(attachment)

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
        server.sendmail(GMAIL_USER, RECIPIENT_EMAIL, msg.as_string())
    print(f"✅ Email enviado para {RECIPIENT_EMAIL}")


def main():
    now = datetime.now()
    print(f"Samba News — {date_str_pt(now)}")

    feeds = {
        "eua": fetch_feeds("eua"),
        "brasil": fetch_feeds("brasil"),
        "economia": fetch_feeds("economia"),
        "tech": fetch_feeds("tech"),
    }

    content = generate_content(feeds)
    html = render_html(content, now)
    subject = f"Samba News — {now.strftime('%d/%m/%Y')} [PREVIEW]"
    send_email(html, subject)
    print("Concluido!")


if __name__ == "__main__":
    main()
