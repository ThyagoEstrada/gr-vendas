"""
GR VENDAS - Importador de PDFs
================================
Processa PDFs de Entradas e Saídas e envia para o Supabase.

INSTALAÇÃO (apenas uma vez):
  pip install pdfplumber requests

COMO USAR:
  1. Coloque os PDFs numa pasta (ex: C:/pdfs)
  2. Execute: python importar_pdfs.py
  3. Informe a pasta quando solicitado

"""

import os
import re
import sys
import json
import requests
import pdfplumber
from datetime import datetime

# ─── CONFIGURAÇÃO ─────────────────────────────────────────────────────────────
SUPABASE_URL = "https://lbrhckgeuigxlpaouyff.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Imxicmhja2dldWlneGxwYW91eWZmIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzY3OTE1NzcsImV4cCI6MjA5MjM2NzU3N30.77oF1jiMcYFBVyRAvmQ8OWdeNz-vmlVL-A1HdXLUmLA"

HEADERS = {
    "Content-Type": "application/json",
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Prefer": "return=representation"
}

# ─── SUPABASE ─────────────────────────────────────────────────────────────────
def sb_get(tabela, query=""):
    r = requests.get(f"{SUPABASE_URL}/rest/v1/{tabela}{query}", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def sb_post(tabela, data):
    if isinstance(data, list):
        # Inserir em lotes de 100
        for i in range(0, len(data), 100):
            lote = data[i:i+100]
            r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabela}", headers=HEADERS, json=lote)
            if not r.ok:
                print(f"  ⚠️  Erro ao inserir lote: {r.text[:200]}")
    else:
        r = requests.post(f"{SUPABASE_URL}/rest/v1/{tabela}", headers=HEADERS, json=data)
        if not r.ok:
            print(f"  ⚠️  Erro: {r.text[:200]}")

def sb_delete(tabela, query):
    r = requests.delete(f"{SUPABASE_URL}/rest/v1/{tabela}{query}", headers=HEADERS)
    if not r.ok:
        print(f"  ⚠️  Erro ao deletar: {r.text[:200]}")

def sb_patch(tabela, data, query):
    r = requests.patch(f"{SUPABASE_URL}/rest/v1/{tabela}{query}", headers=HEADERS, json=data)
    if not r.ok:
        print(f"  ⚠️  Erro ao atualizar: {r.text[:200]}")

# ─── EXTRAIR TEXTO DO PDF ─────────────────────────────────────────────────────
def extrair_texto(path):
    texto = ""
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            t = page.extract_text()
            if t:
                texto += t + "\n"
    return texto

# ─── LIMPAR LINHA (corrigir números fragmentados) ─────────────────────────────
def limpar_linha(line):
    # Corrigir "2 .554,01" → "2.554,01"
    line = re.sub(r'(\d)\s+\.(\d)', r'\1.\2', line)
    # Corrigir "1 14,93" → "114,93" (número fragmentado antes de vírgula)
    line = re.sub(r'\bR\$\s+(\d)\s+(\d+[.,]\d{2})', lambda m: f'R$ {m.group(1)}{m.group(2)}', line)
    # Corrigir "R$ 6 5,19" → "R$ 65,19"
    line = re.sub(r'R\$\s+(\d)\s+(\d+),(\d{2})', lambda m: f'R$ {m.group(1)}{m.group(2)},{m.group(3)}', line)
    # Corrigir "R$ ,21" → "R$ 0,21" e "R$ 2 ,21" → "R$ 2,21"
    line = re.sub(r'(\d)\s+,(\d{2})', r'\1,\2', line)
    return line.strip()

def parse_valor(s):
    """Converte string de valor brasileiro para float."""
    s = s.strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except:
        return 0.0

# ─── DETECTAR TIPO E MÊS/ANO ─────────────────────────────────────────────────
def detectar_info(texto, nome_arquivo=""):
    tipo = "entrada" if ("Relatório de Entradas" in texto or "Data Pedido" in texto) else "saida"
    mes = 0
    ano = datetime.now().year
    fonte = "?"

    # 1. Extrair do nome do arquivo: ENTRADA_01_2026.pdf / SAIDA_04_2026.pdf
    if nome_arquivo:
        nome_upper = nome_arquivo.upper()
        if 'ENTRADA' in nome_upper:
            tipo = 'entrada'
        elif 'SAIDA' in nome_upper or 'SAÍDA' in nome_upper:
            tipo = 'saida'
        m = re.search(r'_(\d{1,2})_(\d{4})', nome_arquivo)
        print(f"   [debug] nome={nome_arquivo} | regex={bool(m)}"
              + (f" mes={m.group(1)} ano={m.group(2)}" if m else " (sem match)"))
        if m:
            mes = int(m.group(1))
            ano = int(m.group(2))
            fonte = "nome_arquivo"

    # 2. Cabeçalho do PDF (fallback)
    if mes == 0:
        m = re.search(r'Mês[:\s]+(\d{1,2})', texto, re.I)
        if m:
            mes = int(m.group(1))
            fonte = "cabecalho_mes"
        m2 = re.search(r'Ano[:\s]+(\d{4})', texto, re.I)
        if m2:
            ano = int(m2.group(1))

    # 3. Primeira data encontrada no texto (último fallback)
    if mes == 0:
        m = re.search(r'(\d{2})/(\d{2})/(\d{4})', texto)
        if m:
            mes = int(m.group(2))
            ano = int(m.group(3))
            fonte = "primeira_data"

    print(f"   [debug] resultado: tipo={tipo} mes={mes} ano={ano} fonte={fonte}")
    return tipo, mes, ano

# ─── PARSER DE ENTRADAS ───────────────────────────────────────────────────────
def parse_entradas(texto, mes, ano):
    linhas = []
    cur_pedido = cur_data = cur_cliente = None
    cur_valor = 0

    for raw in texto.split('\n'):
        line = limpar_linha(raw)
        if not line:
            continue
        if any(x in line for x in ['GR ', 'Relatório', 'ESTRADA THIAGO', 'Mês:', 'Nº Pedido', 'Página', 'Total Geral', 'Total Tabela', 'Total Líquido']):
            continue

        # Formato 2026: "8514 06/01/2026 FARMACIA BRASIL 2.323,00"
        mp = re.match(r'^(\d{4,6})\s+(\d{2}/\d{2}/\d{4})\s+(.+?)\s+([-\d.]+,\d{2})\s*$', line)
        if mp:
            cur_pedido = mp.group(1)
            dp = mp.group(2).split('/')
            cur_data = f"{dp[2]}-{dp[1]}-{dp[0]}"
            cur_cliente = mp.group(3).strip()
            cur_valor = parse_valor(mp.group(4))
            continue

        # Formato 2024: "6032 BRISA EMBALAGENS 11/06/2024 3.974,60"
        mp2 = re.match(r'^(\d{4,6})\s+([A-ZÁÀÃÉÍÓÚÇ].+?)\s+(\d{2}/\d{2}/\d{4})\s+([-\d.]+,\d{2})\s*$', line)
        if mp2:
            cur_pedido = mp2.group(1)
            dp = mp2.group(3).split('/')
            cur_data = f"{dp[2]}-{dp[1]}-{dp[0]}"
            cur_cliente = mp2.group(2).strip()
            cur_valor = parse_valor(mp2.group(4))
            continue

        if not cur_pedido:
            continue

        # Ignorar linhas de observação
        if len(line) > 50 and re.search(r'[A-ZÁÀÃÉÍÓÚÇ]{4,}', line[15:]):
            continue

        # Tabela letra: "A 2,0 840,00"
        mt = re.match(r'^([A-F])\s+([\d,]+|X)\s+([\d.]+,\d{2})\s*$', line, re.I)
        if mt:
            pct = 0 if mt.group(2).upper() == 'X' else parse_valor(mt.group(2))
            linhas.append({
                'mes': mes, 'ano': ano,
                'numero_pedido': cur_pedido, 'data_pedido': cur_data,
                'cliente_nome': cur_cliente, 'tabela_codigo': mt.group(1).upper(),
                'percentual': pct, 'valor': parse_valor(mt.group(3)),
                'eh_estorno': cur_valor < 0
            })
            continue

        # Tabela numérica completa: "148 D3.5 2.176,00"
        mt2 = re.match(r'^(\d{2,4})\s+[DF]([X\d.,]+)\s+([\d.]+,\d{2})\s*$', line, re.I)
        if mt2:
            pct = 0 if mt2.group(2).upper() == 'X' else parse_valor(mt2.group(2))
            linhas.append({
                'mes': mes, 'ano': ano,
                'numero_pedido': cur_pedido, 'data_pedido': cur_data,
                'cliente_nome': cur_cliente, 'tabela_codigo': mt2.group(1),
                'percentual': pct, 'valor': parse_valor(mt2.group(3)),
                'eh_estorno': cur_valor < 0
            })
            continue

        # Tabela numérica só valor: "148 2.176,00"
        mt3 = re.match(r'^(\d{2,4})\s+([\d.]+,\d{2})\s*$', line)
        if mt3:
            linhas.append({
                'mes': mes, 'ano': ano,
                'numero_pedido': cur_pedido, 'data_pedido': cur_data,
                'cliente_nome': cur_cliente, 'tabela_codigo': mt3.group(1),
                'percentual': 0, 'valor': parse_valor(mt3.group(2)),
                'eh_estorno': cur_valor < 0
            })
            continue

        # "D3.5" → atualiza pct da última linha
        mt4 = re.match(r'^D([\d.,]+)\s*$', line, re.I)
        if mt4 and linhas:
            linhas[-1]['percentual'] = parse_valor(mt4.group(1))
            continue

        # "DX" → pct zero
        if re.match(r'^(\d+\s+)?DX\s*$', line, re.I) and linhas:
            linhas[-1]['percentual'] = 0

    return linhas

# ─── PARSER DE SAÍDAS ─────────────────────────────────────────────────────────
def parse_saidas(texto, mes, ano):
    linhas = []
    for raw in texto.split('\n'):
        line = limpar_linha(raw)
        if not line:
            continue
        if any(line.startswith(x) for x in ['ESTRADA', 'Nº PEDIDO', 'TOTAL', 'COMISSÃO +']):
            continue
        if 'Página' in line:
            continue

        # Formato Dez/2025: "128236 GRUPO ZAFFANI 142117 R$ 1.103,90 D 3,5 4,5 R$ 49,68"
        m = re.match(
            r'^([\d\/]+|\*)\s+(.+?)\s+(\d{4,7}|\*)\s+R\$\s*([\d.]+,\d{2})\s+([A-F])\s+([\d,X]+)\s*([\d,]*)\s*R\$\s*([\d.,]*|-)\s*$',
            line, re.I
        )
        if m:
            pct = 0 if m.group(6).upper() == 'X' else parse_valor(m.group(6))
            extra = parse_valor(m.group(7)) if m.group(7) else 0
            com_s = m.group(8).strip()
            com = 0 if com_s in ['-', ''] else parse_valor(com_s)
            linhas.append({
                'mes': mes, 'ano': ano,
                'numero_pedido': m.group(1), 'cliente_nome': m.group(2).strip(),
                'nf': m.group(3),
                'valor': parse_valor(m.group(4)),
                'tabela_codigo': m.group(5).upper(),
                'percentual': pct, 'extra': extra, 'comissao': com
            })
            continue

        # Formato Jun/2024 com extra: "97918 VITALE 115937 2.554,01 R$ D 3,5 4,5 114,93 R$"
        m2 = re.match(
            r'^([\d\/]+|\*)\s+(.+?)\s+(\d{4,7}|\*)\s+([\d.]+,\d{2})\s+R\$\s+([A-F])\s+([\d,X]+)\s*([\d,]*)\s+([\d.,]+)\s+R\$\s*$',
            line, re.I
        )
        if m2:
            pct = 0 if m2.group(6).upper() == 'X' else parse_valor(m2.group(6))
            extra = parse_valor(m2.group(7)) if m2.group(7) else 0
            com = parse_valor(m2.group(8))
            linhas.append({
                'mes': mes, 'ano': ano,
                'numero_pedido': m2.group(1), 'cliente_nome': m2.group(2).strip(),
                'nf': m2.group(3),
                'valor': parse_valor(m2.group(4)),
                'tabela_codigo': m2.group(5).upper(),
                'percentual': pct, 'extra': extra, 'comissao': com
            })
            continue

        # Formato Jun/2024 sem extra: "98641 NSA CC 116814 1.474,20 R$ A 2 29,48 R$"
        m3 = re.match(
            r'^([\d\/]+|\*)\s+(.+?)\s+(\d{4,7}|\*)\s+([\d.]+,\d{2})\s+R\$\s+([A-F])\s+([\d,X]+)\s+([\d.,]+)\s+R\$\s*$',
            line, re.I
        )
        if m3:
            pct = 0 if m3.group(6).upper() == 'X' else parse_valor(m3.group(6))
            com = parse_valor(m3.group(7))
            linhas.append({
                'mes': mes, 'ano': ano,
                'numero_pedido': m3.group(1), 'cliente_nome': m3.group(2).strip(),
                'nf': m3.group(3),
                'valor': parse_valor(m3.group(4)),
                'tabela_codigo': m3.group(5).upper(),
                'percentual': pct, 'extra': 0, 'comissao': com
            })

    return linhas

# ─── VINCULAR PEDIDOS MANUAIS AO PDF ─────────────────────────────────────────
def vincular_pedidos(linhas, mes, ano):
    """Cruza pedidos sem numero_pedido com entradas do PDF (fuzzy >= 85%, valor +-10%)."""
    import calendar
    from difflib import SequenceMatcher

    print(f"   🔗 Iniciando vinculação de pedidos manuais...")

    # Agregar valor total por numero_pedido (soma das linhas de tabela, sem estornos)
    ent_map = {}
    for l in linhas:
        if l.get('eh_estorno'):
            continue
        np = l['numero_pedido']
        if np not in ent_map:
            ent_map[np] = {'numero_pedido': np, 'cliente_nome': l['cliente_nome'],
                           'data_pedido': l['data_pedido'], 'valor': 0.0, 'matched': False}
        ent_map[np]['valor'] += l['valor']

    print(f"   🔗 {len(ent_map)} pedido(s) distintos no PDF")

    # Pedidos sem numero_pedido do mesmo mês/ano
    primeiro = f"{ano}-{mes:02d}-01"
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    ultimo = f"{ano}-{mes:02d}-{ultimo_dia:02d}"
    pedidos_sem_np = sb_get('pedidos',
        f'?numero_pedido=is.null'
        f'&data_pedido=gte.{primeiro}&data_pedido=lte.{ultimo}'
        f'&select=id,cliente_id,valor_total,data_pedido')

    print(f"   🔗 {len(pedidos_sem_np)} pedido(s) manual(is) encontrado(s) para {mes:02d}/{ano}")

    if not pedidos_sem_np:
        # Checar entradas sem pedido mesmo sem manuais
        sem_pedido = list(ent_map.values())
        if sem_pedido:
            print(f"   📋 {len(sem_pedido)} entrada(s) no PDF sem pedido lançado")
        return

    clientes = sb_get('clientes', '?select=id,nome')
    cli_map = {c['id']: c['nome'] for c in clientes}

    vinculados, sem_match = [], []

    for ped in pedidos_sem_np:
        ped_nome = cli_map.get(ped['cliente_id'], '').upper().strip()
        ped_valor = float(ped['valor_total'] or 0)
        best_np, best_score = None, 0.0

        for np, ent in ent_map.items():
            if ent['matched']:
                continue
            score = SequenceMatcher(None, ped_nome, ent['cliente_nome'].upper().strip()).ratio()
            if score < 0.85:
                continue
            max_v = max(ped_valor, ent['valor'])
            if max_v > 0 and abs(ped_valor - ent['valor']) / max_v > 0.10:
                continue
            if score > best_score:
                best_score, best_np = score, np

        if best_np:
            ent_map[best_np]['matched'] = True
            sb_patch('pedidos',
                {'numero_pedido': best_np, 'status': 'Importado',
                 'valor_total': ent_map[best_np]['valor'],
                 'updated_at': datetime.now().isoformat()},
                f'?id=eq.{ped["id"]}')
            vinculados.append({'pedido_id': ped['id'], 'numero_pedido': best_np,
                               'cliente': cli_map.get(ped['cliente_id'], '?'),
                               'score': round(best_score * 100)})
        else:
            sem_match.append({'pedido_id': ped['id'],
                              'cliente': cli_map.get(ped['cliente_id'], '?'),
                              'valor': ped_valor})

    sem_pedido = [e for e in ent_map.values() if not e['matched']]

    # Limpar divergências anteriores deste tipo e registrar novas
    sb_delete('divergencias', f'?campo_divergente=eq.nao_encontrado_no_pdf&mes=eq.{mes}&ano=eq.{ano}')
    sb_delete('divergencias', f'?campo_divergente=eq.pedido_nao_lancado&mes=eq.{mes}&ano=eq.{ano}')
    divs = []
    for p in sem_match:
        divs.append({'tipo': 'entrada', 'mes': mes, 'ano': ano,
                     'numero_pedido': f'PED_{p["pedido_id"]}',
                     'campo_divergente': 'nao_encontrado_no_pdf',
                     'valor_pdf': '—', 'valor_sistema': p['cliente']})
    for e in sem_pedido:
        divs.append({'tipo': 'entrada', 'mes': mes, 'ano': ano,
                     'numero_pedido': e['numero_pedido'],
                     'campo_divergente': 'pedido_nao_lancado',
                     'valor_pdf': str(round(e['valor'], 2)), 'valor_sistema': '—'})
    if divs:
        sb_post('divergencias', divs)

    print(f"   ✅ {len(vinculados)} pedido(s) vinculado(s) com sucesso")
    for v in vinculados:
        print(f"      → {v['cliente']} ↔ NP {v['numero_pedido']} ({v['score']}%)")
    if sem_match:
        print(f"   ⚠️  {len(sem_match)} pedido(s) seu(s) sem match no PDF")
        for p in sem_match:
            print(f"      → {p['cliente']} | R$ {p['valor']:,.2f}")
    if sem_pedido:
        print(f"   📋 {len(sem_pedido)} entrada(s) do PDF sem pedido seu")
        for e in sem_pedido:
            print(f"      → {e['numero_pedido']} | {e['cliente_nome']} | R$ {e['valor']:,.2f}")


# ─── CONFERIR DIVERGÊNCIAS DE ENTRADA ────────────────────────────────────────
def conferir_entradas(linhas, mes, ano):
    pedidos = sb_get('pedidos', '?select=numero_pedido,valor_total')
    map_ped = {p['numero_pedido']: p for p in pedidos}
    ag = {}
    for l in linhas:
        if l['numero_pedido'] not in ag:
            ag[l['numero_pedido']] = l
    divs = []
    for np, l in ag.items():
        if np not in map_ped:
            divs.append({'tipo': 'entrada', 'mes': mes, 'ano': ano, 'numero_pedido': np,
                        'campo_divergente': 'nao_encontrado', 'valor_pdf': np, 'valor_sistema': 'não cadastrado'})
        elif abs(float(map_ped[np]['valor_total'] or 0) - l['valor']) > 0.10:
            divs.append({'tipo': 'entrada', 'mes': mes, 'ano': ano, 'numero_pedido': np,
                        'campo_divergente': 'valor', 'valor_pdf': str(l['valor']),
                        'valor_sistema': str(map_ped[np]['valor_total'])})
    return divs

# ─── VINCULAR PEDIDOS MANUAIS AO PDF ─────────────────────────────────────────
def vincular_pedidos(linhas, mes, ano):
    """Cruza pedidos sem numero_pedido com entradas do PDF (fuzzy >= 85%, valor +-10%)."""
    import calendar
    from difflib import SequenceMatcher

    print(f"\n🔗 Vinculando pedidos manuais ao PDF de {mes:02d}/{ano}...")

    # Agregar valor total por numero_pedido (soma das linhas de tabela, sem estornos)
    ent_map = {}
    for l in linhas:
        if l.get('eh_estorno'):
            continue
        np = l['numero_pedido']
        if np not in ent_map:
            ent_map[np] = {'numero_pedido': np, 'cliente_nome': l['cliente_nome'],
                           'data_pedido': l['data_pedido'], 'valor': 0.0, 'matched': False}
        ent_map[np]['valor'] += l['valor']

    # Pedidos sem numero_pedido do mesmo mês/ano
    primeiro = f"{ano}-{mes:02d}-01"
    ultimo_dia = calendar.monthrange(ano, mes)[1]
    ultimo = f"{ano}-{mes:02d}-{ultimo_dia:02d}"
    pedidos_sem_np = sb_get('pedidos',
        f'?numero_pedido=is.null'
        f'&data_pedido=gte.{primeiro}&data_pedido=lte.{ultimo}'
        f'&select=id,cliente_id,valor_total,data_pedido')

    clientes = sb_get('clientes', '?select=id,nome')
    cli_map = {c['id']: c['nome'] for c in clientes}

    vinculados, sem_match = [], []

    for ped in pedidos_sem_np:
        ped_nome = cli_map.get(ped['cliente_id'], '').upper().strip()
        ped_valor = float(ped['valor_total'] or 0)
        best_np, best_score = None, 0.0

        for np, ent in ent_map.items():
            if ent['matched']:
                continue
            score = SequenceMatcher(None, ped_nome, ent['cliente_nome'].upper().strip()).ratio()
            if score < 0.85:
                continue
            max_v = max(ped_valor, ent['valor'])
            if max_v > 0 and abs(ped_valor - ent['valor']) / max_v > 0.10:
                continue
            if score > best_score:
                best_score, best_np = score, np

        if best_np:
            ent_map[best_np]['matched'] = True
            sb_patch('pedidos',
                {'numero_pedido': best_np, 'status': 'Importado',
                 'valor_total': ent_map[best_np]['valor'],
                 'updated_at': datetime.now().isoformat()},
                f'?id=eq.{ped["id"]}')
            vinculados.append({'pedido_id': ped['id'], 'numero_pedido': best_np,
                               'cliente': cli_map.get(ped['cliente_id'], '?'),
                               'score': round(best_score * 100)})
        else:
            sem_match.append({'pedido_id': ped['id'],
                              'cliente': cli_map.get(ped['cliente_id'], '?'),
                              'valor': ped_valor})

    sem_pedido = [e for e in ent_map.values() if not e['matched']]

    # Limpar divergências anteriores deste tipo e registrar novas
    sb_delete('divergencias', f'?campo_divergente=eq.nao_encontrado_no_pdf&mes=eq.{mes}&ano=eq.{ano}')
    sb_delete('divergencias', f'?campo_divergente=eq.pedido_nao_lancado&mes=eq.{mes}&ano=eq.{ano}')
    divs = []
    for p in sem_match:
        divs.append({'tipo': 'entrada', 'mes': mes, 'ano': ano,
                     'numero_pedido': f'PED_{p["pedido_id"]}',
                     'campo_divergente': 'nao_encontrado_no_pdf',
                     'valor_pdf': '—', 'valor_sistema': p['cliente']})
    for e in sem_pedido:
        divs.append({'tipo': 'entrada', 'mes': mes, 'ano': ano,
                     'numero_pedido': e['numero_pedido'],
                     'campo_divergente': 'pedido_nao_lancado',
                     'valor_pdf': str(round(e['valor'], 2)), 'valor_sistema': '—'})
    if divs:
        sb_post('divergencias', divs)

    print(f"   ✅ {len(vinculados)} pedido(s) vinculado(s) com sucesso")
    for v in vinculados:
        print(f"      → {v['cliente']} ↔ NP {v['numero_pedido']} ({v['score']}%)")
    print(f"   ⚠️  {len(sem_match)} pedido(s) seu(s) sem match no PDF (lançou mas não entrou)")
    for p in sem_match:
        print(f"      → {p['cliente']} | R$ {p['valor']:,.2f}")
    print(f"   📋 {len(sem_pedido)} entrada(s) do PDF sem pedido seu (não lançou)")
    for e in sem_pedido:
        print(f"      → {e['numero_pedido']} | {e['cliente_nome']} | R$ {e['valor']:,.2f}")

    return {'vinculados': len(vinculados), 'sem_match': len(sem_match), 'sem_pedido': len(sem_pedido)}


# ─── PROCESSAR UM PDF ─────────────────────────────────────────────────────────
def processar_pdf(path):
    nome = os.path.basename(path)
    print(f"\n📄 Processando: {nome}")

    try:
        texto = extrair_texto(path)
        tipo, mes, ano = detectar_info(texto, os.path.basename(path))
        MESES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']
        mes_nome = MESES[mes-1] if 1 <= mes <= 12 else str(mes)
        print(f"   Tipo: {tipo.upper()} | Período: {mes_nome}/{ano}")

        if tipo == 'entrada':
            linhas = parse_entradas(texto, mes, ano)
            print(f"   Extraídas: {len(linhas)} linhas")

            if not linhas:
                print("   ⚠️  Nenhuma linha extraída. Verifique o formato do PDF.")
                return

            # Salvar entradas
            sb_delete('entradas', f'?mes=eq.{mes}&ano=eq.{ano}')
            sb_post('entradas', linhas)

            # Conferir divergências
            divs = conferir_entradas(linhas, mes, ano)
            sb_delete('divergencias', f'?tipo=eq.entrada&mes=eq.{mes}&ano=eq.{ano}')
            if divs:
                sb_post('divergencias', divs)
                print(f"   ⚠️  {len(divs)} divergência(s) encontrada(s)")
            else:
                print(f"   ✅ Sem divergências")

            # Vincular pedidos manuais do mesmo período
            vincular_pedidos(linhas, mes, ano)

            total = sum(l['valor'] for l in linhas if not l['eh_estorno'])
            print(f"   💰 Total líquido: R$ {total:,.2f}")

        else:  # saida
            linhas = parse_saidas(texto, mes, ano)
            print(f"   Extraídas: {len(linhas)} linhas")

            if not linhas:
                print("   ⚠️  Nenhuma linha extraída. Verifique o formato do PDF.")
                return

            # Salvar saídas
            sb_delete('saidas', f'?mes=eq.{mes}&ano=eq.{ano}')
            sb_post('saidas', linhas)

            # Conferir divergências de comissão
            divs = []
            for l in linhas:
                if l['tabela_codigo'] == 'X' or l['comissao'] == 0:
                    continue
                calc = l['valor'] * (l['percentual'] + l['extra']) / 100
                if abs(calc - l['comissao']) > 0.05:
                    divs.append({
                        'tipo': 'saida', 'mes': mes, 'ano': ano,
                        'numero_pedido': l['numero_pedido'],
                        'campo_divergente': 'comissao',
                        'valor_pdf': str(l['comissao']),
                        'valor_sistema': f"{calc:.2f}"
                    })
            sb_delete('divergencias', f'?tipo=eq.saida&mes=eq.{mes}&ano=eq.{ano}')
            if divs:
                sb_post('divergencias', divs)
                print(f"   ⚠️  {len(divs)} divergência(s) de comissão")
            else:
                print(f"   ✅ Comissões conferidas")

            total_val = sum(l['valor'] for l in linhas)
            total_com = sum(l['comissao'] for l in linhas)
            print(f"   💰 Faturado: R$ {total_val:,.2f} | Comissão: R$ {total_com:,.2f}")

        print(f"   ✅ Concluído!")

    except Exception as e:
        print(f"   ❌ Erro: {e}")
        import traceback
        traceback.print_exc()

# ─── MENU PRINCIPAL ───────────────────────────────────────────────────────────
def main():
    print("=" * 55)
    print("  GR VENDAS — Importador de PDFs")
    print("  Thiago Estrada")
    print("=" * 55)

    # Verificar conexão com Supabase
    print("\n🔌 Verificando conexão com o banco de dados...")
    try:
        r = sb_get('clientes', '?select=id&limit=1')
        print("   ✅ Conectado ao Supabase!")
    except Exception as e:
        print(f"   ❌ Erro de conexão: {e}")
        input("\nPressione Enter para sair...")
        return

    print("\nEscolha uma opção:")
    print("  1 - Processar um PDF específico")
    print("  2 - Processar todos os PDFs de uma pasta")
    print("  3 - Sair")

    opcao = input("\nOpção: ").strip()

    if opcao == '1':
        caminho = input("Caminho do PDF: ").strip().strip('"')
        if os.path.exists(caminho):
            processar_pdf(caminho)
        else:
            print(f"❌ Arquivo não encontrado: {caminho}")

    elif opcao == '2':
        pasta = input("Caminho da pasta com os PDFs: ").strip().strip('"')
        if not os.path.isdir(pasta):
            print(f"❌ Pasta não encontrada: {pasta}")
        else:
            pdfs = sorted([f for f in os.listdir(pasta) if f.lower().endswith('.pdf')])
            if not pdfs:
                print("❌ Nenhum PDF encontrado na pasta.")
            else:
                print(f"\n📂 {len(pdfs)} PDF(s) encontrado(s):")
                for f in pdfs:
                    print(f"   • {f}")
                confirm = input(f"\nProcessar todos? (s/n): ").strip().lower()
                if confirm == 's':
                    ok = 0
                    for f in pdfs:
                        processar_pdf(os.path.join(pasta, f))
                        ok += 1
                    print(f"\n✅ {ok} arquivo(s) processado(s)!")

    print("\n" + "=" * 55)
    input("Pressione Enter para sair...")

if __name__ == '__main__':
    main()
