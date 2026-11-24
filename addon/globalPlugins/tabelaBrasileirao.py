import globalPluginHandler
import ui
import urllib.request
import json
import re
import tones
import wx
import gui
import time
import os
import threading
from logHandler import log
import addonHandler

addonHandler.initTranslation()
from gettext import gettext as _

CACHE_TTL_SECONDS = 1800
HTTP_TIMEOUT_SECONDS = 12
LOADING_BEEP_INTERVAL_MS = 1800

# Servidor do desenvolvedor: cache atualizado periodicamente (leitura rápida).
REMOTE_JSON_URL_A = "https://www.leandross.com.br/tabela/cache_tabela_A.json"
REMOTE_JSON_URL_B = "https://www.leandross.com.br/tabela/cache_tabela_B.json"

# Fonte original, consultada pelo botão "Atualizar tabela" (dados do momento).
TERRA_URL_A = "https://www.terra.com.br/esportes/futebol/brasileiro-serie-a/tabela/"
TERRA_URL_B = "https://www.terra.com.br/esportes/futebol/brasileiro-serie-b/tabela/"

# A página do Terra é bem maior que o JSON, por isso timeout e limite próprios.
HTTP_TIMEOUT_TERRA_SECONDS = 25
TERRA_MAX_BYTES = 4 * 1024 * 1024

# Abaixo disso consideramos que a página não traz a tabela esperada: fim de
# temporada, página de playoff, ou mudança de layout no Terra.
TERRA_MIN_TIMES = 16


def _safe_makedirs(path: str) -> str:
	try:
		os.makedirs(path, exist_ok=True)
		return path
	except Exception:
		fallback = os.path.join(os.path.expanduser("~"), "cache_tabela_brasileirao")
		os.makedirs(fallback, exist_ok=True)
		return fallback


def _read_json(path: str):
	try:
		with open(path, "r", encoding="utf-8") as f:
			return json.load(f)
	except Exception:
		return None


def _write_json_atomic(path: str, data) -> None:
	tmp = f"{path}.tmp"
	with open(tmp, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False)
	os.replace(tmp, path)


try:
	import config
	BASE_DIR = os.path.join(config.getUserConfigPath(), "cache_tabela_brasileirao")
except Exception:
	BASE_DIR = os.path.join(os.environ.get("APPDATA", ""), "nvda", "cache_tabela_brasileirao")

BASE_DIR = _safe_makedirs(BASE_DIR)
CACHE_FILE_A = os.path.join(BASE_DIR, "cache_tabela_A.json")
CACHE_FILE_B = os.path.join(BASE_DIR, "cache_tabela_B.json")


# ===========================================================================
# Leitura da classificação direto do Terra (fonte original)
#
# Usada pelo botão "Atualizar tabela", para trazer a classificação no momento
# em que o usuário pede, sem depender do intervalo de atualização do servidor.
#
# Propositalmente escrito só com o módulo re. O Python que acompanha o NVDA
# não traz a biblioteca padrão completa, então nada de html.parser aqui.
# ===========================================================================

_TERRA_RE_TABELA = re.compile(r"<table\b[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
_TERRA_RE_TABELA_ABERTA = re.compile(r"<table\b[^>]*>", re.IGNORECASE)
_TERRA_RE_LINHA = re.compile(r"<tr\b([^>]*)>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_TERRA_RE_CELULA = re.compile(r"<t([dh])\b([^>]*)>(.*?)</t\1>", re.IGNORECASE | re.DOTALL)

_TERRA_RE_CLASSE = re.compile(r"""\bclass\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_TERRA_RE_TITULO = re.compile(r"""\btitle\s*=\s*["']([^"']*)["']""", re.IGNORECASE)
_TERRA_RE_IDTEAM = re.compile(r"""\bdata-idteam\s*=\s*["']([^"']*)["']""", re.IGNORECASE)

_TERRA_RE_TAG = re.compile(r"<[^>]*>")
_TERRA_RE_ESPACOS = re.compile(r"\s+")
_TERRA_RE_ENTIDADE = re.compile(r"&(#[0-9]+|#[xX][0-9a-fA-F]+|[a-zA-Z]+);")

_TERRA_RE_SUFIXO_NOME = re.compile(r"\s*>>\s*$")
_TERRA_RE_NUMERO = re.compile(r"-?\d+")
_TERRA_RE_SUBIU = re.compile(r"Subiu\s*(\d+)", re.IGNORECASE)
_TERRA_RE_DESCEU = re.compile(r"Desceu\s*(\d+)", re.IGNORECASE)

_TERRA_FAIXAS_POR_ZONA = (
	(re.compile(r"\bzone-1\b"), "libertadores"),
	(re.compile(r"\bzone-2\b"), "pre-libertadores"),
	(re.compile(r"\bzone-3\b"), "sul-americana"),
	(re.compile(r"\bzone-4\b"), "rebaixados"),
)

# Entidades que aparecem em nome de time e em texto de tabela. O pacote html
# da biblioteca padrão não está garantido no NVDA, por isso a lista é local.
_TERRA_ENTIDADES = {
	"amp": "&", "lt": "<", "gt": ">", "quot": '"', "apos": "'",
	"nbsp": " ", "ndash": "-", "mdash": "-", "hellip": "...",
	"aacute": "á", "agrave": "à", "atilde": "ã", "acirc": "â",
	"eacute": "é", "ecirc": "ê", "iacute": "í", "oacute": "ó",
	"otilde": "õ", "ocirc": "ô", "uacute": "ú", "uuml": "ü",
	"ccedil": "ç", "ntilde": "ñ",
	"Aacute": "Á", "Atilde": "Ã", "Acirc": "Â", "Eacute": "É",
	"Ecirc": "Ê", "Iacute": "Í", "Oacute": "Ó", "Otilde": "Õ",
	"Ocirc": "Ô", "Uacute": "Ú", "Ccedil": "Ç",
}

_TERRA_SIGLAS = {
	"Palmeiras": "PAL", "São Paulo": "SAO", "Corinthians": "COR",
	"Bahia": "BAH", "Fluminense": "FLU", "Athletico-PR": "CAP",
	"Bragantino": "BGT", "Grêmio": "GRE", "Chapecoense": "CHA",
	"Mirassol": "MIR", "Flamengo": "FLA", "Coritiba": "CFC",
	"Santos": "SAN", "Botafogo": "BOT", "Vitória": "VIT", "Remo": "REM",
	"Atlético-MG": "CAM", "Internacional": "INT", "Cruzeiro": "CRU",
	"Vasco da Gama": "VAS", "Vasco": "VAS", "Ceará": "CEA",
	"Fortaleza": "FOR", "Juventude": "JUV", "Sport": "SPT",
	"Novorizontino": "NOV", "Goiás": "GOI", "Atlético-GO": "ACG",
	"Vila Nova": "VIL", "Criciúma": "CRI", "Avaí": "AVA", "CRB": "CRB",
	"Operário-PR": "OPE", "Amazonas": "AMA", "Paysandu": "PAY",
	"Botafogo-SP": "BFC", "Ferroviária": "FER", "América-MG": "AME",
	"Athletic": "ATH", "Cuiabá": "CUI", "Volta Redonda": "VRE",
}


def _terra_desescapar(texto: str) -> str:
	"""Converte as entidades HTML mais comuns, sem usar o pacote html."""
	def troca(m):
		e = m.group(1)
		if e.startswith("#"):
			try:
				if e[1] in ("x", "X"):
					return chr(int(e[2:], 16))
				return chr(int(e[1:]))
			except Exception:
				return m.group(0)
		return _TERRA_ENTIDADES.get(e, m.group(0))
	return _TERRA_RE_ENTIDADE.sub(troca, texto)


def _terra_texto_limpo(html: str) -> str:
	"""Tira as tags de dentro de uma célula e normaliza os espaços."""
	sem_tag = _TERRA_RE_TAG.sub(" ", html)
	return _TERRA_RE_ESPACOS.sub(" ", _terra_desescapar(sem_tag)).strip()


def _terra_atributo(regex, attrs: str) -> str:
	m = regex.search(attrs or "")
	return m.group(1) if m else ""


def _terra_linhas(html: str):
	"""Lista as linhas das tabelas do documento, cada uma com suas células."""
	blocos = _TERRA_RE_TABELA.findall(html)
	if not blocos:
		# tabela sem fechamento: considera daí até o fim do documento
		m = _TERRA_RE_TABELA_ABERTA.search(html)
		if not m:
			return []
		blocos = [html[m.end():]]

	linhas = []
	for bloco in blocos:
		for attrs_linha, conteudo in _TERRA_RE_LINHA.findall(bloco):
			celulas = []
			for _tag, attrs_celula, html_celula in _TERRA_RE_CELULA.findall(conteudo):
				celulas.append({
					"class": _terra_atributo(_TERRA_RE_CLASSE, attrs_celula),
					"title": _terra_desescapar(_terra_atributo(_TERRA_RE_TITULO, attrs_celula)),
					"text": _terra_texto_limpo(html_celula),
				})
			if celulas:
				linhas.append({
					"class": _terra_atributo(_TERRA_RE_CLASSE, attrs_linha),
					"idteam": _terra_atributo(_TERRA_RE_IDTEAM, attrs_linha),
					"celulas": celulas,
				})
	return linhas


def _terra_int(valor) -> int:
	if not valor:
		return 0
	m = _TERRA_RE_NUMERO.search(str(valor).replace("%", "").replace(".", ""))
	if not m:
		return 0
	try:
		return int(m.group(0))
	except Exception:
		return 0


def _terra_celula_por_classe(celulas, fragmento: str) -> str:
	for c in celulas:
		if fragmento in c.get("class", ""):
			return c.get("text", "")
	return ""


def _terra_tem_classe(celulas, fragmento: str) -> bool:
	for c in celulas:
		if fragmento in c.get("class", ""):
			return True
	return False


def _terra_celula_por_titulo(celulas, titulo: str) -> str:
	for c in celulas:
		if c.get("title", "") == titulo:
			return c.get("text", "")
	return ""


def _terra_faixa(classe: str):
	for regex, nome in _TERRA_FAIXAS_POR_ZONA:
		if regex.search(classe):
			return nome
	return None


def _terra_variacao(celulas) -> int:
	"""Quantas posições o time subiu (positivo) ou desceu (negativo).

	O número vem do texto da célula ("Subiu1", "Desceu2"), presente apenas
	para quem mudou de posição. A classe da célula não serve para isso: o
	Terra marca "movement up" até em quem não se moveu, inclusive no líder.
	"""
	texto = _terra_celula_por_classe(celulas, "movement")
	if not texto:
		return 0
	m = _TERRA_RE_SUBIU.search(texto)
	if m:
		return int(m.group(1))
	m = _TERRA_RE_DESCEU.search(texto)
	if m:
		return -int(m.group(1))
	return 0


def _terra_parsear_classificacao(html: str):
	"""Converte o HTML do Terra na mesma estrutura dos JSONs do servidor."""
	try:
		linhas = _terra_linhas(html or "")
	except Exception:
		log.debugWarning("Tabela do Brasileirão: falha ao separar as linhas da tabela", exc_info=True)
		return []

	dados = []
	posicoes_vistas = set()

	for linha in linhas:
		celulas = linha.get("celulas") or []
		if not celulas or not _terra_tem_classe(celulas, "team-name"):
			continue

		nome = _TERRA_RE_SUFIXO_NOME.sub("", _terra_celula_por_classe(celulas, "team-name")).strip()
		if not nome:
			continue

		pos = _terra_int(_terra_celula_por_classe(celulas, "position"))
		if pos <= 0 or pos in posicoes_vistas:
			continue
		posicoes_vistas.add(pos)

		idteam = linha.get("idteam") or ""
		pontos = _terra_celula_por_classe(celulas, "points") or _terra_celula_por_titulo(celulas, "Pontos")

		dados.append({
			"posicao": pos,
			"pontos": _terra_int(pontos),
			"time": {
				"time_id": int(idteam) if idteam.isdigit() else None,
				"nome_popular": nome,
				"sigla": _TERRA_SIGLAS.get(nome),
			},
			"jogos": _terra_int(_terra_celula_por_titulo(celulas, "Jogos")),
			"vitorias": _terra_int(_terra_celula_por_titulo(celulas, "Vitórias")),
			"empates": _terra_int(_terra_celula_por_titulo(celulas, "Empates")),
			"derrotas": _terra_int(_terra_celula_por_titulo(celulas, "Derrotas")),
			"gols_pro": _terra_int(_terra_celula_por_titulo(celulas, "Gols Pró")),
			"gols_contra": _terra_int(_terra_celula_por_titulo(celulas, "Gols Contra")),
			"saldo_gols": _terra_int(_terra_celula_por_titulo(celulas, "Saldo de Gols")),
			"aproveitamento": _terra_int(_terra_celula_por_titulo(celulas, "Aproveitamento")),
			"variacao_posicao": _terra_variacao(celulas),
			"ultimos_jogos": [],
			"faixa_classificacao": _terra_faixa(linha.get("class") or ""),
		})

	dados.sort(key=lambda it: it.get("posicao", 0))
	return dados

class ErrorDialog(wx.MessageDialog):
	def __init__(self, parent=None):
		super().__init__(
			parent or gui.mainFrame,
			_("Não foi possível carregar os dados da tabela.\nTente mais tarde."),
			_("Tabela do Brasileirão"),
			wx.OK | wx.ICON_WARNING
		)


class TabelaDialog(wx.Dialog):
	def __init__(self, dados, serie="A", onForceRefresh=None, onOpenSerieA=None, onOpenSerieB=None):
		super(TabelaDialog, self).__init__(
			gui.mainFrame,
			title=_("Classificação do Brasileirão — Série B") if (serie or "").upper() == "B" else _("Classificação do Brasileirão — Série A"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		self.dados = dados or []
		self.serie = (serie or "A").upper()
		self._onForceRefresh = onForceRefresh
		self._onOpenSerieA = onOpenSerieA
		self._onOpenSerieB = onOpenSerieB

		mainSizer = wx.BoxSizer(wx.VERTICAL)

		listPanel = wx.Panel(self)
		listSizer = wx.BoxSizer(wx.VERTICAL)
		self.lista = wx.ListCtrl(listPanel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SIMPLE)
		listSizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 6)
		listPanel.SetSizer(listSizer)
		mainSizer.Add(listPanel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

		self.lista.InsertColumn(0, _("Tabela de classificação"), width=900)

		try:
			f = self.lista.GetFont()
			pt = f.GetPointSize()
			if pt and pt > 0:
				f.SetPointSize(pt + 2)
				self.lista.SetFont(f)
		except Exception:
			pass

		self._popular_lista()

		try:
			branco = wx.Colour(255, 255, 255)
			cinza = wx.Colour(245, 245, 245)
			for i in range(self.lista.GetItemCount()):
				self.lista.SetItemBackgroundColour(i, branco if (i % 2 == 0) else cinza)
		except Exception:
			pass

		self.lista.Bind(wx.EVT_SIZE, self._ao_redimensionar_lista)
		self._ajustar_largura_coluna()

		self.lista.Bind(wx.EVT_KEY_DOWN, self.ao_pressionar_setas)
		self.lista.Bind(wx.EVT_CHAR, self.ao_pressionar_letras)
		self.Bind(wx.EVT_CHAR_HOOK, self.ao_pressionar_esc)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)

		self.btnAtualizar = wx.Button(self, wx.ID_ANY, _("Atualizar tabela"))
		btnSizer.Add(self.btnAtualizar, 0)

		self.btnSerieA = wx.Button(self, wx.ID_ANY, _("Tabela Série A"))
		btnSizer.Add(self.btnSerieA, 0)

		self.btnSerieB = wx.Button(self, wx.ID_ANY, _("Tabela Série B"))
		btnSizer.Add(self.btnSerieB, 0)

		self.btnCopiar = wx.Button(self, wx.ID_ANY, _("Copiar tabela"))
		btnSizer.Add(self.btnCopiar, 0)

		self.btnSalvar = wx.Button(self, wx.ID_ANY, _("Salvar em TXT"))
		btnSizer.Add(self.btnSalvar, 0)

		btnSizer.AddStretchSpacer(1)

		self.btnFechar = wx.Button(self, wx.ID_CANCEL, _("Fechar"))
		try:
			self.btnFechar.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
			self.btnAtualizar.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
			self.btnCopiar.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
			self.btnSalvar.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
			self.btnSerieA.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
			self.btnSerieB.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
		except Exception:
			pass

		btnSizer.Add(self.btnFechar, 0)
		mainSizer.Add(btnSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

		self.btnAtualizar.Bind(wx.EVT_BUTTON, self._on_click_atualizar)
		self.btnSerieA.Bind(wx.EVT_BUTTON, self._on_click_serie_a)
		self.btnSerieB.Bind(wx.EVT_BUTTON, self._on_click_serie_b)
		self.btnCopiar.Bind(wx.EVT_BUTTON, lambda evt: self._copiar_tabela_para_area_de_transferencia())
		self.btnSalvar.Bind(wx.EVT_BUTTON, lambda evt: self._salvar_tabela_em_txt())

		if not callable(self._onForceRefresh):
			self.btnAtualizar.Disable()

		try:
			if self.serie == "A":
				self.btnSerieA.Disable()
			else:
				self.btnSerieB.Disable()
		except Exception:
			pass

		self.SetSizer(mainSizer)
		self.Maximize(True)
		self.Raise()

		count = self.lista.GetItemCount()
		if count > 0:
			self.lista.SetFocus()
			self.lista.SetItemState(0, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
			self.lista.EnsureVisible(0)
		else:
			self.lista.SetFocus()

	def _popular_lista(self):
		try:
			self.lista.DeleteAllItems()
		except Exception:
			pass

		for i, item in enumerate(self.dados):
			equipe = item.get("equipe") or item.get("time") or {}
			nome = equipe.get("nome_popular") or _("Time")
			pos = item.get("posicao", "?")
			pts = item.get("pontos", 0)
			self.lista.InsertItem(i, f"{pos}º {nome} - {pts} " + _("pontos"))

	def _nome_do_time_selecionado(self):
		idx = self.lista.GetFirstSelected()
		if idx < 0 or idx >= len(self.dados or []):
			return None
		equipe = self.dados[idx].get("equipe") or self.dados[idx].get("time") or {}
		return equipe.get("nome_popular")

	def _indice_do_time(self, nome):
		if not nome:
			return -1
		for i, item in enumerate(self.dados or []):
			equipe = item.get("equipe") or item.get("time") or {}
			if equipe.get("nome_popular") == nome:
				return i
		return -1

	def _atualizar_dados_na_tela(self, novos_dados):
		# Guarda o time que estava selecionado para voltar nele depois. Quem
		# clica em "Atualizar tabela" quase sempre quer ver se aquele time
		# mudou de posição, e voltar ao 1º colocado faria perder o lugar.
		nome_antes = self._nome_do_time_selecionado()

		self.dados = novos_dados or []
		self._popular_lista()
		self._ajustar_largura_coluna()

		total = self.lista.GetItemCount()
		if total <= 0:
			return

		idx = self._indice_do_time(nome_antes)
		if idx < 0:
			idx = 0
		self.lista.SetFocus()
		self.lista.SetItemState(idx, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
		self.lista.EnsureVisible(idx)

	def _set_atualizando(self, updating: bool):
		try:
			self.btnAtualizar.Enable(not updating)
			self.btnFechar.Enable(not updating)
			if updating:
				self.btnAtualizar.SetLabel(_("Atualizando..."))
			else:
				self.btnAtualizar.SetLabel(_("Atualizar tabela"))
		except Exception:
			pass

	def _on_click_atualizar(self, event):
		if not callable(self._onForceRefresh):
			return

		self._set_atualizando(True)
		tones.beep(880, 60)
		ui.message(_("Atualizando dados da tabela..."))

		def ok(novos_dados, origem="servidor"):
			try:
				self._set_atualizando(False)
				self._atualizar_dados_na_tela(novos_dados)
			except RuntimeError:
				# A janela foi fechada enquanto a busca corria (o Esc fecha
				# mesmo com o botão Fechar desabilitado). Nada a atualizar.
				return
			tones.beep(660, 40)
			if origem == "fonte":
				ui.message(_("Tabela atualizada agora, direto da fonte."))
			elif origem == "sem_classificacao":
				# Campeonato entre temporadas ou em fase de playoff: não existe
				# classificação nova para buscar, e isso não é falha nenhuma.
				ui.message(_("Esta série ainda não tem classificação nova. Mostrando os últimos dados."))
			else:
				ui.message(_("Tabela atualizada."))

		def fail(silencioso=False):
			try:
				self._set_atualizando(False)
			except RuntimeError:
				return  # janela já fechada
			if silencioso:
				# Usado quando não houve erro, só não era o momento de buscar.
				return
			tones.beep(220, 120)
			dlg = ErrorDialog(self)
			try:
				dlg.ShowModal()
			finally:
				dlg.Destroy()

		try:
			self._onForceRefresh(ok, fail)
		except Exception:
			fail()

	def _on_click_serie_a(self, event):
		if callable(self._onOpenSerieA):
			try:
				self._onOpenSerieA(self)
			except Exception:
				pass

	def _on_click_serie_b(self, event):
		if callable(self._onOpenSerieB):
			try:
				self._onOpenSerieB(self)
			except Exception:
				pass

	def _ajustar_largura_coluna(self):
		try:
			w = self.lista.GetClientSize().GetWidth()
			if w and w > 40:
				self.lista.SetColumnWidth(0, max(40, w - 8))
		except Exception:
			pass

	def _mostrar_ajuda(self):
		dlg = wx.Dialog(self, title=_("Ajuda"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		texto = wx.TextCtrl(
			dlg,
			wx.ID_ANY,
			"""Botões da janela:

- Atualizar tabela: busca a classificação do momento, direto da fonte. É o
  que usar durante os jogos. Se a fonte não responder, o complemento usa o
  servidor automaticamente.
- Tabela Série A e Tabela Série B: troca de série.
- Copiar tabela: copia a tabela inteira.
- Salvar em TXT: grava a tabela num arquivo de texto.
- Fechar: fecha a janela.

Atalhos disponíveis:

- Control + Shift + T: abre a tabela (atalho global do NVDA).
- Esc: fecha a janela.
- Setas para cima/baixo: navega na lista e anuncia classificação, time e pontos.
- F1: abre esta ajuda.
- Ctrl+C: copia a linha selecionada (classificação - time - pontos).
- Ctrl+A: copia a tabela inteira (classificação - time - pontos).
- Ctrl+S: salva a tabela em TXT (classificação - time - pontos).

Atalhos para obter dados (time selecionado):

- V: Vitórias
- E: Empates
- D: Derrotas
- S: Saldo de gols
- J: Jogos
- P: Gols pró
- C: Gols contra
- A: Aproveitamento

Pressione Esc para voltar à tabela.""",
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
		)
		texto.SetMinSize((520, 320))
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(texto, 1, wx.EXPAND | wx.ALL, 10)
		dlg.SetSizerAndFit(sizer)
		dlg.CentreOnParent()

		def onKey(event):
			if event.GetKeyCode() == wx.WXK_ESCAPE:
				dlg.EndModal(wx.ID_CANCEL)
				return
			event.Skip()

		dlg.Bind(wx.EVT_CHAR_HOOK, onKey)
		texto.SetFocus()
		try:
			dlg.ShowModal()
		finally:
			dlg.Destroy()
			try:
				self.lista.SetFocus()
			except Exception:
				pass

	def _ao_redimensionar_lista(self, event):
		self._ajustar_largura_coluna()
		event.Skip()

	def _gerar_texto_tabela_simples(self) -> str:
		linhas = []
		for item in (self.dados or []):
			equipe = item.get("equipe") or item.get("time") or {}
			nome = equipe.get("nome_popular") or _("Time")
			pos = item.get("posicao", "")
			pts = item.get("pontos", "")
			linhas.append(f"{pos}º - {nome} - {pts}")
		return "\n".join(linhas)

	def _copiar_texto(self, texto: str) -> bool:
		"""Põe o texto na área de transferência. Devolve se conseguiu mesmo.

		O Open() falha quando outro programa está com a área de transferência
		presa. Antes o complemento anunciava "copiado" de qualquer forma, e o
		usuário só descobria ao tentar colar.
		"""
		try:
			if not wx.TheClipboard.Open():
				return False
			try:
				wx.TheClipboard.SetData(wx.TextDataObject(texto))
				wx.TheClipboard.Flush()
				return True
			finally:
				wx.TheClipboard.Close()
		except Exception:
			log.debugWarning("Tabela do Brasileirão: falha ao copiar", exc_info=True)
			return False

	def _copiar_linha_selecionada(self):
		idx = self.lista.GetFirstSelected()
		if idx < 0 or idx >= len(self.dados):
			ui.message(_("Nenhum time selecionado."))
			return
		item = self.dados[idx]
		equipe = item.get("equipe") or item.get("time") or {}
		nome = equipe.get("nome_popular") or _("Time")
		pos = item.get("posicao", "")
		pts = item.get("pontos", "")
		texto = f"{pos}º - {nome} - {pts}"
		if self._copiar_texto(texto):
			ui.message(_("Copiado: {linha}").format(linha=texto))
		else:
			ui.message(_("Não foi possível copiar."))

	def _copiar_tabela_para_area_de_transferencia(self):
		texto = self._gerar_texto_tabela_simples()
		if not texto:
			ui.message(_("A tabela está vazia."))
			return
		if self._copiar_texto(texto):
			ui.message(_("Tabela copiada."))
		else:
			ui.message(_("Não foi possível copiar a tabela."))

	def _salvar_tabela_em_txt(self):
		texto = self._gerar_texto_tabela_simples()
		nomePadrao = _("Tabela do Brasileirão — Série B.txt") if self.serie == "B" else _("Tabela do Brasileirão — Série A.txt")
		try:
			dlg = wx.FileDialog(
				self,
				message=_("Salvar tabela em TXT"),
				defaultDir=os.path.expanduser("~"),
				defaultFile=nomePadrao,
				wildcard=_("Arquivo de texto (*.txt)|*.txt"),
				style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
			)
			try:
				if dlg.ShowModal() != wx.ID_OK:
					return
				caminho = dlg.GetPath()
			finally:
				dlg.Destroy()
			with open(caminho, "w", encoding="utf-8") as f:
				f.write(texto)
			ui.message(_("Tabela salva em arquivo TXT."))
		except Exception:
			ui.message(_("Não foi possível salvar o arquivo."))

	def ao_pressionar_esc(self, event):
		keyCode = event.GetKeyCode()

		if event.ControlDown() and not event.AltDown():
			if keyCode in (ord("C"), ord("c")):
				self._copiar_linha_selecionada()
				return
			if keyCode in (ord("A"), ord("a")):
				self._copiar_tabela_para_area_de_transferencia()
				return
			if keyCode in (ord("S"), ord("s")):
				self._salvar_tabela_em_txt()
				return

		if keyCode == wx.WXK_F1:
			self._mostrar_ajuda()
			return
		if keyCode == wx.WXK_ESCAPE:
			self.Close()
		else:
			event.Skip()

	def ao_pressionar_setas(self, event):
		codigo = event.GetKeyCode()
		idx = self.lista.GetFirstSelected()
		total = self.lista.GetItemCount()
		if idx == -1 or total <= 0:
			event.Skip()
			return
		if codigo == wx.WXK_UP and idx == 0:
			tones.beep(200, 30)
			return
		if codigo == wx.WXK_DOWN and idx == total - 1:
			tones.beep(200, 30)
			return
		event.Skip()

	def ao_pressionar_letras(self, event):
		codigo = event.GetKeyCode()
		if codigo >= 256:
			event.Skip()
			return
		try:
			tecla = chr(codigo).upper()
		except Exception:
			event.Skip()
			return

		idx = self.lista.GetFirstSelected()
		if idx == -1 or idx >= len(self.dados):
			event.Skip()
			return

		it = self.dados[idx]
		nome = (it.get("equipe") or it.get("time") or {}).get("nome_popular", _("Time"))
		mapa = {
			"V": "vitorias", "E": "empates", "D": "derrotas", "S": "saldo_gols",
			"J": "jogos", "P": "gols_pro", "C": "gols_contra", "A": "aproveitamento",
		}
		nomes = {
			"V": _("Vitórias"), "E": _("Empates"), "D": _("Derrotas"), "S": _("Saldo"),
			"J": _("Jogos"), "P": _("Gols pró"), "C": _("Gols contra"), "A": _("Aproveitamento"),
		}

		if tecla not in mapa:
			event.Skip()
			return

		chave = mapa[tecla]

		if chave == "gols_pro":
			valor = it.get("gols_pro", it.get("golsPro", it.get("golspro", 0)))
			ui.message(f"{nome}: {nomes[tecla]} {valor}")
			return

		if chave == "gols_contra":
			valor = it.get("gols_contra", it.get("golsContra", it.get("golscontra", 0)))
			ui.message(f"{nome}: {nomes[tecla]} {valor}")
			return

		if chave == "aproveitamento":
			valor = it.get("aproveitamento", None)
			if valor is None:
				pontos = it.get("pontos", it.get("ponto", 0))
				jogos = it.get("jogos", 0)
				try:
					pontos = float(pontos)
					jogos = float(jogos)
				except Exception:
					pontos = 0.0
					jogos = 0.0
				valor = (pontos / (jogos * 3.0)) * 100.0 if jogos > 0 else 0.0
			try:
				if isinstance(valor, str):
					txt = valor.strip()
					if txt and not txt.endswith("%"):
						txt = txt + "%"
					ui.message(f"{nome}: {nomes[tecla]} {txt}")
				else:
					pct = float(valor)
					txt = f"{pct:.1f}".replace(".", ",") + "%"
					ui.message(f"{nome}: {nomes[tecla]} {txt}")
			except Exception:
				ui.message(f"{nome}: {nomes[tecla]} {valor}")
			return

		valor = it.get(chave, 0)
		ui.message(f"{nome}: {nomes[tecla]} {valor}")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	scriptCategory = _("Tabela Brasileirão")

	def __init__(self, *args, **kwargs):
		super(GlobalPlugin, self).__init__(*args, **kwargs)
		self._fetchInProgress = False
		self._toolsMenu = None
		self._toolsMenuItemOpen = None
		self._loadingTimer = None
		self._add_tools_menu_items()

	def terminate(self):
		self._stop_loading_timer()
		self._remove_tools_menu_items()
		super(GlobalPlugin, self).terminate()

	def _add_tools_menu_items(self):
		try:
			mainFrame = getattr(gui, "mainFrame", None)
			if not mainFrame:
				return
			sysTray = getattr(mainFrame, "sysTrayIcon", None)
			if not sysTray:
				return
			toolsMenu = getattr(sysTray, "toolsMenu", None)
			if not toolsMenu:
				return
			self._toolsMenu = toolsMenu
			self._toolsMenuItemOpen = toolsMenu.Append(
				wx.ID_ANY,
				_("Tabela do Brasileirão"),
				_("Abrir a tabela do Brasileirão")
			)
			sysTray.Bind(wx.EVT_MENU, self._on_tools_menu_open, self._toolsMenuItemOpen)
		except Exception:
			log.exception("Falha ao adicionar itens no menu Ferramentas")

	def _remove_tools_menu_items(self):
		try:
			mainFrame = getattr(gui, "mainFrame", None)
			sysTray = getattr(mainFrame, "sysTrayIcon", None) if mainFrame else None
			for item, handler in ((self._toolsMenuItemOpen, self._on_tools_menu_open),):
				if self._toolsMenu and item:
					try:
						if sysTray:
							sysTray.Unbind(wx.EVT_MENU, handler=handler, source=item)
					except Exception:
						pass
					try:
						self._toolsMenu.Remove(item)
					except Exception:
						pass
					try:
						item.Destroy()
					except Exception:
						pass
		finally:
			self._toolsMenu = None
			self._toolsMenuItemOpen = None

	def _on_tools_menu_open(self, event):
		self.script_tabela(None)

	def _start_loading_timer(self):
		def _start():
			try:
				self._stop_loading_timer()
				mainFrame = getattr(gui, "mainFrame", None)
				if not mainFrame:
					return
				self._loadingTimer = wx.Timer(mainFrame)
				mainFrame.Bind(wx.EVT_TIMER, self._on_loading_timer, self._loadingTimer)
				self._loadingTimer.Start(LOADING_BEEP_INTERVAL_MS)
			except Exception:
				log.exception("Falha ao iniciar timer de carregamento")
		wx.CallAfter(_start)

	def _stop_loading_timer(self):
		def _stop():
			try:
				mainFrame = getattr(gui, "mainFrame", None)
				if self._loadingTimer and mainFrame:
					try:
						mainFrame.Unbind(wx.EVT_TIMER, handler=self._on_loading_timer, source=self._loadingTimer)
					except Exception:
						pass
					try:
						self._loadingTimer.Stop()
					except Exception:
						pass
					try:
						self._loadingTimer.Destroy()
					except Exception:
						pass
			finally:
				self._loadingTimer = None
		wx.CallAfter(_stop)

	def _on_loading_timer(self, event):
		try:
			if self._fetchInProgress:
				tones.beep(660, 15)
			else:
				self._stop_loading_timer()
		except Exception:
			pass

	def _mostrar_erro_simples(self):
		try:
			tones.beep(220, 120)
			dlg = ErrorDialog(gui.mainFrame)
			try:
				dlg.ShowModal()
			finally:
				dlg.Destroy()
		except Exception:
			ui.message(_("Não foi possível carregar os dados da tabela. Tente mais tarde."))

	def _cache_file_for_serie(self, serie: str) -> str:
		return CACHE_FILE_B if (serie or "A").upper() == "B" else CACHE_FILE_A

	def _url_for_serie(self, serie: str) -> str:
		return REMOTE_JSON_URL_B if (serie or "A").upper() == "B" else REMOTE_JSON_URL_A

	def _url_terra_for_serie(self, serie: str) -> str:
		return TERRA_URL_B if (serie or "A").upper() == "B" else TERRA_URL_A

	def _carregar_cache(self, serie: str):
		cache = _read_json(self._cache_file_for_serie(serie))
		if not isinstance(cache, dict):
			return None
		timestamp = cache.get("timestamp")
		dados = cache.get("dados")
		if not isinstance(timestamp, (int, float)) or not isinstance(dados, list):
			return None
		if (time.time() - float(timestamp)) >= CACHE_TTL_SECONDS:
			return None
		return dados

	def _carregar_cache_stale(self, serie: str):
		cache = _read_json(self._cache_file_for_serie(serie))
		if not isinstance(cache, dict):
			return (None, None)
		timestamp = cache.get("timestamp")
		dados = cache.get("dados")
		if not isinstance(timestamp, (int, float)) or not isinstance(dados, list):
			return (None, None)
		idade = time.time() - float(timestamp)
		if idade < 0:
			idade = 0
		return (dados, idade)

	def _salvar_cache(self, serie: str, dados):
		try:
			_write_json_atomic(self._cache_file_for_serie(serie), {"timestamp": time.time(), "dados": dados})
		except Exception:
			log.exception("Falha ao salvar cache")

	def _baixar_json_em_thread(self, serie: str, on_ok, on_fail):
		url = self._url_for_serie(serie)

		def worker():
			try:
				req = urllib.request.Request(
					url,
					headers={
						"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
						"Accept": "application/json",
						"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
					},
				)
				with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
					payload = resp.read().decode("utf-8", errors="replace")
				obj = json.loads(payload)
				if isinstance(obj, dict) and isinstance(obj.get("dados"), list):
					dados = obj.get("dados")
				elif isinstance(obj, list):
					dados = obj
				else:
					raise ValueError("JSON inválido")
				self._salvar_cache(serie, dados)
				wx.CallAfter(on_ok, dados)
			except Exception:
				wx.CallAfter(on_fail)
			finally:
				self._fetchInProgress = False
				self._stop_loading_timer()

		self._fetchInProgress = True
		self._start_loading_timer()
		threading.Thread(target=worker, name="TabelaBrasileiraoFetch", daemon=True).start()

	def _mostrar_tabela(self, dados, serie: str):
		try:
			def openA(currentDlg):
				self._open_serie_substituindo("A", currentDlg)

			def openB(currentDlg):
				self._open_serie_substituindo("B", currentDlg)

			dlg = TabelaDialog(
				dados,
				serie=serie,
				onForceRefresh=lambda ok, fail: self._force_refresh_from_dialog(serie, ok, fail),
				onOpenSerieA=openA if serie.upper() == "B" else None,
				onOpenSerieB=openB if serie.upper() == "A" else None,
			)
			dlg.ShowModal()
		except Exception:
			log.exception("Falha ao exibir diálogo de tabela")

	def _force_refresh_from_dialog(self, serie: str, ok, fail):
		"""Botão "Atualizar tabela": lê a classificação direto do Terra, para o
		usuário ver o resultado do momento. Se o Terra não responder, ou a
		página não trouxer a tabela, cai no servidor como plano B."""
		if self._fetchInProgress:
			# Não é erro: outra busca já está em andamento. Só devolvemos o
			# botão ao estado normal, sem diálogo de erro.
			ui.message(_("Aguarde, já estou buscando dados."))
			fail(True)
			return

		def terra_ok(dados):
			ok(dados, "fonte")

		def terra_falhou(sem_classificacao=False):
			# Só avisamos da troca de fonte quando foi problema de acesso. Se a
			# página simplesmente não tem classificação, a mensagem final já
			# explica isso, e avisar duas vezes só confunde.
			if not sem_classificacao:
				ui.message(_("Fonte indisponível. Buscando no servidor."))
			origem = "sem_classificacao" if sem_classificacao else "servidor"
			self._baixar_json_em_thread(serie, lambda dados: ok(dados, origem), fail)

		self._baixar_do_terra_em_thread(serie, terra_ok, terra_falhou)

	def _baixar_do_terra_em_thread(self, serie: str, on_ok, on_fail):
		url = self._url_terra_for_serie(serie)

		def worker():
			# Distingue os dois motivos de falha: a página respondeu mas não
			# traz classificação (entre temporadas, fase de playoff), ou houve
			# problema de acesso. Cada caso merece uma mensagem diferente.
			sem_classificacao = False
			try:
				req = urllib.request.Request(
					url,
					headers={
						"User-Agent": (
							"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
							"AppleWebKit/537.36 (KHTML, like Gecko) "
							"Chrome/124.0 Safari/537.36"
						),
						"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
						"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
					},
				)
				with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_TERRA_SECONDS) as resp:
					bruto = resp.read(TERRA_MAX_BYTES)
				dados = _terra_parsear_classificacao(bruto.decode("utf-8", errors="replace"))
				if len(dados) < TERRA_MIN_TIMES:
					sem_classificacao = True
					raise ValueError(
						"Página sem a tabela de classificação (%d linhas)" % len(dados)
					)
				self._salvar_cache(serie, dados)
				wx.CallAfter(on_ok, dados)
			except Exception:
				log.debugWarning("Tabela do Brasileirão: falha ao ler direto da fonte", exc_info=True)
				wx.CallAfter(on_fail, sem_classificacao)
			finally:
				self._fetchInProgress = False
				self._stop_loading_timer()

		self._fetchInProgress = True
		self._start_loading_timer()
		threading.Thread(target=worker, name="TabelaBrasileiraoTerraFetch", daemon=True).start()

	def _open_serie_substituindo(self, serie: str, dlgAtual=None):
		"""Abre uma nova série e só fecha a janela atual se tudo correr bem."""
		serie = (serie or "A").upper()

		if self._fetchInProgress:
			ui.message(_("Aguarde, buscando dados."))
			return

		dados_cache = self._carregar_cache(serie)
		if dados_cache is not None:
			tones.beep(440, 30)
			try:
				if dlgAtual:
					dlgAtual.Close()
			except Exception:
				pass
			wx.CallAfter(lambda: self._mostrar_tabela(dados_cache, serie))
			return

		tones.beep(880, 50)
		ui.message(_("Buscando dados da tabela."))

		def ok(dados):
			try:
				if dlgAtual:
					dlgAtual.Close()
			except Exception:
				pass
			self._mostrar_tabela(dados, serie)

		def fail():
			dados_cache_stale, _idade = self._carregar_cache_stale(serie)
			if dados_cache_stale is not None:
				ui.message(_("Mostrando dados do cache."))
				try:
					if dlgAtual:
						dlgAtual.Close()
				except Exception:
					pass
				self._mostrar_tabela(dados_cache_stale, serie)
			else:
				self._mostrar_erro_simples()
				# janela atual permanece aberta

		self._baixar_json_em_thread(serie, ok, fail)

	def _open_serie(self, serie: str):
		serie = (serie or "A").upper()

		if self._fetchInProgress:
			ui.message(_("Aguarde, buscando dados."))
			return

		dados_cache = self._carregar_cache(serie)
		if dados_cache is not None:
			tones.beep(440, 30)
			wx.CallAfter(lambda: self._mostrar_tabela(dados_cache, serie))
			return

		tones.beep(880, 50)
		ui.message(_("Buscando dados da tabela."))

		def ok(dados):
			self._mostrar_tabela(dados, serie)

		def fail():
			dados_cache_stale, _idade = self._carregar_cache_stale(serie)
			if dados_cache_stale is not None:
				ui.message(_("Mostrando dados do cache."))
				self._mostrar_tabela(dados_cache_stale, serie)
			else:
				self._mostrar_erro_simples()

		self._baixar_json_em_thread(serie, ok, fail)

	def script_tabela(self, gesture):
		self._open_serie("A")

	__gestures = {
		"kb:control+shift+t": "tabela",
	}
