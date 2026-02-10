import globalPluginHandler
import ui
import urllib.request
import urllib.error
import json
import tones
import wx
import gui
import time
import os
import threading
import webbrowser
import base64
import ctypes
from ctypes import wintypes
from logHandler import log
import addonHandler

addonHandler.initTranslation()
from gettext import gettext as _

CACHE_TTL_SECONDS = 1800
HTTP_TIMEOUT_SECONDS = 12
LOADING_BEEP_INTERVAL_MS = 1800

# Chave gratuita liberada pela API Futebol para uso no add-on
FREE_API_KEY = "live_1be3551b4e1eb7e7eb355a2824b9fa"
WIDGET_URL = "https://widget.api-futebol.com.br/render/widget_2d27f839ac107d06"


def _safe_makedirs(path: str) -> str:
	try:
		os.makedirs(path, exist_ok=True)
		return path
	except Exception:
		fallback = os.path.join(os.path.expanduser("~"), "tabela_futebol_config")
		os.makedirs(fallback, exist_ok=True)
		return fallback


def _read_json(path: str):
	try:
		with open(path, "r", encoding="utf-8") as f:
			return json.load(f)
	except Exception:
		return None


def _write_json_atomic(path: str, data):
	tmp = f"{path}.tmp"
	with open(tmp, "w", encoding="utf-8") as f:
		json.dump(data, f, ensure_ascii=False)
	os.replace(tmp, path)


class DATA_BLOB(ctypes.Structure):
	_fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

crypt32.CryptProtectData.argtypes = [
	ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR,
	ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
	ctypes.c_void_p, wintypes.DWORD,
	ctypes.POINTER(DATA_BLOB)
]
crypt32.CryptProtectData.restype = wintypes.BOOL

crypt32.CryptUnprotectData.argtypes = [
	ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR),
	ctypes.POINTER(DATA_BLOB), ctypes.c_void_p,
	ctypes.c_void_p, wintypes.DWORD,
	ctypes.POINTER(DATA_BLOB)
]
crypt32.CryptUnprotectData.restype = wintypes.BOOL

kernel32.LocalFree.argtypes = [ctypes.c_void_p]
kernel32.LocalFree.restype = ctypes.c_void_p


def _dpapi_protect(plaintext: str) -> str:
	if not isinstance(plaintext, str) or not plaintext:
		return ""
	data = plaintext.encode("utf-8")
	in_blob = DATA_BLOB(len(data), (ctypes.c_byte * len(data)).from_buffer_copy(data))
	out_blob = DATA_BLOB()
	if not crypt32.CryptProtectData(ctypes.byref(in_blob), "NVDA Add-on API Key", None, None, None, 0, ctypes.byref(out_blob)):
		raise OSError(ctypes.get_last_error())
	try:
		encrypted = ctypes.string_at(out_blob.pbData, out_blob.cbData)
		return "dpapi:" + base64.b64encode(encrypted).decode("ascii")
	finally:
		kernel32.LocalFree(out_blob.pbData)


def _dpapi_unprotect(protected: str) -> str:
	if not isinstance(protected, str) or not protected:
		return ""
	if protected.startswith("dpapi:"):
		protected = protected[6:]
	enc = base64.b64decode(protected.encode("ascii"))
	in_blob = DATA_BLOB(len(enc), (ctypes.c_byte * len(enc)).from_buffer_copy(enc))
	out_blob = DATA_BLOB()
	desc = wintypes.LPWSTR()
	if not crypt32.CryptUnprotectData(ctypes.byref(in_blob), ctypes.byref(desc), None, None, None, 0, ctypes.byref(out_blob)):
		raise OSError(ctypes.get_last_error())
	try:
		plaintext = ctypes.string_at(out_blob.pbData, out_blob.cbData).decode("utf-8", errors="strict")
		return plaintext
	finally:
		if desc:
			kernel32.LocalFree(desc)
		kernel32.LocalFree(out_blob.pbData)




def _extract_http_error_detail(err):
	try:
		body = err.read()
	except Exception:
		return ""
	try:
		text = body.decode("utf-8", errors="replace") if isinstance(body, (bytes, bytearray)) else str(body)
	except Exception:
		return ""
	text = (text or "").strip()
	if not text:
		return ""
	try:
		obj = json.loads(text)
		if isinstance(obj, dict):
			for k in ("message", "mensagem", "erro", "error", "detail", "details"):
				val = obj.get(k)
				if isinstance(val, str) and val.strip():
					return val.strip()
			return json.dumps(obj, ensure_ascii=False)
	except Exception:
		pass
	return text

try:
	import config
	BASE_DIR = os.path.join(config.getUserConfigPath(), "tabela_futebol_config")
except Exception:
	BASE_DIR = os.path.join(os.environ.get("APPDATA", ""), "nvda", "tabela_futebol_config")

BASE_DIR = _safe_makedirs(BASE_DIR)
CONFIG_FILE = os.path.join(BASE_DIR, "settings.json")
CACHE_FILE = os.path.join(BASE_DIR, "cache_tabela.json")

def _read_settings():
	cfg = _read_json(CONFIG_FILE)
	return cfg if isinstance(cfg, dict) else {}

def _write_settings(cfg: dict):
	try:
		_write_json_atomic(CONFIG_FILE, cfg if isinstance(cfg, dict) else {})
	except Exception:
		log.exception("Falha ao salvar configurações")


class ConfigDialog(wx.Dialog):
	def __init__(self, parent, initialValue=""):
		super(ConfigDialog, self).__init__(
			parent,
			title=_("Configurar chave da API Futebol"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX,
		)
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(
			wx.StaticText(self, label=_("Cole sua chave (live_...) abaixo:")),
			0,
			wx.ALL,
			10,
		)
		self.txt_chave = wx.TextCtrl(self, size=(500, -1), value=initialValue or "")
		sizer.Add(self.txt_chave, 0, wx.EXPAND | wx.ALL, 10)
		btn_sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		sizer.Add(btn_sizer, 0, wx.ALIGN_CENTER | wx.ALL, 10)
		self.SetSizer(sizer)
		self.Maximize(True)
		self.Raise()
		self.txt_chave.SetFocus()

class ErrorDetailsDialog(wx.Dialog):
	def __init__(self, parent, summary: str, details: str):
		super(ErrorDetailsDialog, self).__init__(
			parent,
			title=_("Detalhes do erro"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER | wx.MAXIMIZE_BOX,
		)
		mainSizer = wx.BoxSizer(wx.VERTICAL)

		lbl = wx.StaticText(self, label=summary or "")
		mainSizer.Add(lbl, 0, wx.EXPAND | wx.ALL, 10)

		self.txt = wx.TextCtrl(
			self,
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2 | wx.HSCROLL,
			value=details or "",
			size=(820, 420),
		)
		mainSizer.Add(self.txt, 1, wx.EXPAND | wx.LEFT | wx.RIGHT, 10)

		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		btnSizer.AddStretchSpacer(1)
		self.btnCopy = wx.Button(self, wx.ID_ANY, _("Copiar detalhes do erro"))
		self.btnOk = wx.Button(self, wx.ID_OK, _("OK"))
		btnSizer.Add(self.btnCopy, 0, wx.RIGHT, 8)
		btnSizer.Add(self.btnOk, 0)
		mainSizer.Add(btnSizer, 0, wx.EXPAND | wx.ALL, 10)

		self.btnCopy.Bind(wx.EVT_BUTTON, self._onCopy)

		self.SetSizer(mainSizer)
		self.Maximize(True)
		self.Raise()
		self.txt.SetFocus()

	def _onCopy(self, event):
		try:
			if wx.TheClipboard.Open():
				try:
					data = wx.TextDataObject(self.txt.GetValue() or "")
					wx.TheClipboard.SetData(data)
					wx.TheClipboard.Flush()
					ui.message(_("Detalhes copiados."))
				finally:
					wx.TheClipboard.Close()
		except Exception:
			log.exception("Falha ao copiar detalhes do erro")
			ui.message(_("Não foi possível copiar os detalhes."))


class TabelaDialog(wx.Dialog):
	def __init__(self, dados, onTrocarChave=None, onAbrirWidget=None):
		super(TabelaDialog, self).__init__(
			gui.mainFrame,
			title=_("Classificação do Brasileirão — Série A"),
			style=wx.DEFAULT_DIALOG_STYLE | wx.MAXIMIZE_BOX | wx.RESIZE_BORDER,
		)
		self.dados = dados or []
		self._onTrocarChave = onTrocarChave
		self._onAbrirWidget = onAbrirWidget

		mainSizer = wx.BoxSizer(wx.VERTICAL)

		rotuloFonte = wx.StaticText(self, label=_("Fonte: www.api-futebol.com.br"))
		mainSizer.Add(rotuloFonte, 0, wx.LEFT | wx.RIGHT | wx.TOP, 10)

		# Painel para dar “margem interna” em volta da lista (evita ficar colada na borda)
		listPanel = wx.Panel(self)
		listSizer = wx.BoxSizer(wx.VERTICAL)
		self.lista = wx.ListCtrl(listPanel, style=wx.LC_REPORT | wx.LC_SINGLE_SEL | wx.BORDER_SIMPLE)
		listSizer.Add(self.lista, 1, wx.EXPAND | wx.ALL, 6)
		listPanel.SetSizer(listSizer)
		mainSizer.Add(listPanel, 1, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, 10)

		self.lista.InsertColumn(0, _("Tabela de classificação"), width=900)

		# Fonte um pouco maior para melhorar a leitura (aumenta também a altura das linhas)
		try:
			f = self.lista.GetFont()
			pt = f.GetPointSize()
			if pt and pt > 0:
				f.SetPointSize(pt + 2)
				self.lista.SetFont(f)
		except Exception:
			pass

		for i, item in enumerate(self.dados):
			equipe = item.get("equipe") or item.get("time") or {}
			nome = equipe.get("nome_popular") or _("Time")
			pos = item.get("posicao", "?")
			pts = item.get("pontos", 0)
			self.lista.InsertItem(i, f"{pos}º {nome} - {pts} " + _("pontos"))

		# Zebra leve
		try:
			branco = wx.Colour(255, 255, 255)
			cinza = wx.Colour(245, 245, 245)
			for i in range(self.lista.GetItemCount()):
				self.lista.SetItemBackgroundColour(i, branco if (i % 2 == 0) else cinza)
		except Exception:
			pass

		# Ajusta a largura da coluna para ocupar a janela (reduz o “vazio” à direita)
		self.lista.Bind(wx.EVT_SIZE, self._ao_redimensionar_lista)
		self._ajustar_largura_coluna()

		# Teclas de navegação / atalhos
		self.lista.Bind(wx.EVT_KEY_DOWN, self.ao_pressionar_setas)
		self.lista.Bind(wx.EVT_CHAR, self.ao_pressionar_letras)
		self.Bind(wx.EVT_CHAR_HOOK, self.ao_pressionar_esc)

		# Botões no canto inferior direito, com espaçamento igual
		btnSizer = wx.BoxSizer(wx.HORIZONTAL)
		btnSizer.AddStretchSpacer(1)

		self.btnWidget = wx.Button(self, wx.ID_ANY, _("Ver no navegador"))
		self.btnTrocar = wx.Button(self, wx.ID_ANY, _("Trocar chave API"))
		self.btnFechar = wx.Button(self, wx.ID_CANCEL, _("Fechar"))

		# Deixar o “Fechar” mais discreto (quando disponível)
		try:
			self.btnFechar.SetWindowVariant(wx.WINDOW_VARIANT_SMALL)
		except Exception:
			pass

		btnSizer.Add(self.btnWidget, 0, wx.RIGHT, 8)
		btnSizer.Add(self.btnTrocar, 0, wx.RIGHT, 8)
		btnSizer.Add(self.btnFechar, 0)

		mainSizer.Add(btnSizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

		self.btnWidget.Bind(wx.EVT_BUTTON, self._ao_abrir_widget)
		self.btnTrocar.Bind(wx.EVT_BUTTON, self._ao_trocar_chave)

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

	def _ajustar_largura_coluna(self):
		try:
			w = self.lista.GetClientSize().GetWidth()
			if w and w > 40:
				self.lista.SetColumnWidth(0, max(40, w - 8))
		except Exception:
			pass

	def _mostrar_ajuda(self):
		# Janela de ajuda sem botão OK; fecha com Esc e volta o foco para a tabela
		dlg = wx.Dialog(self, title=_("Ajuda"), style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
		texto = wx.TextCtrl(
			dlg,
			wx.ID_ANY,
			"""Atalhos disponíveis:

- Control + Shift + T: abre a tabela.
- Esc: fecha a tabela.
- Setas para cima/baixo: navega na lista e anuncia classificação, time e pontos.
- F1: abre esta ajuda.

Atalhos para obter dados (time selecionado):

- V: Vitórias
- E: Empates
- D: Derrotas
- S: Saldo de gols
- J: Jogos
- P: Gols pró
- C: Gols contra
- A: Aproveitamento

Caminhando com Tab, você encontrará os botões:

- Trocar chave API: informar uma nova chave
- Ver no navegador: abrir a visualização web no navegador padrão

Pressione Esc para voltar à tabela.""",
			style=wx.TE_MULTILINE | wx.TE_READONLY | wx.TE_RICH2,
		)
		texto.SetMinSize((520, 320))
		sizer = wx.BoxSizer(wx.VERTICAL)
		sizer.Add(texto, 1, wx.EXPAND | wx.ALL, 10)
		dlg.SetSizerAndFit(sizer)
		dlg.CentreOnParent()

		def onKey(event):
			keyCode = event.GetKeyCode()
			if keyCode == wx.WXK_ESCAPE:
				dlg.EndModal(wx.ID_CANCEL)
				return
			event.Skip()

		dlg.Bind(wx.EVT_CHAR_HOOK, onKey)
		texto.SetFocus()
		try:
			dlg.ShowModal()
		finally:
			dlg.Destroy()
			# Volta o foco para a lista da tabela, se possível
			try:
				if hasattr(self, "lista"):
					self.lista.SetFocus()
				else:
					self.SetFocus()
			except Exception:
				pass

	def _ao_redimensionar_lista(self, event):
		self._ajustar_largura_coluna()
		event.Skip()

	def _ao_abrir_widget(self, event):
		if callable(self._onAbrirWidget):
			self._onAbrirWidget()

	def _ao_trocar_chave(self, event):
		if callable(self._onTrocarChave):
			self._onTrocarChave(self)

	def ao_pressionar_esc(self, event):
		keyCode = event.GetKeyCode()
		if keyCode == wx.WXK_F1:
			self._mostrar_ajuda()
			return
		if event.GetKeyCode() == wx.WXK_ESCAPE:
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
		mapa = {"V": "vitorias", "E": "empates", "D": "derrotas", "S": "saldo_gols", "J": "jogos", "P": "gols_pro", "C": "gols_contra", "A": "aproveitamento"}
		nomes = {"V": _("Vitórias"), "E": _("Empates"), "D": _("Derrotas"), "S": _("Saldo"), "J": _("Jogos"), "P": _("Gols pró"), "C": _("Gols contra"), "A": _("Aproveitamento")}

		if tecla in mapa:
			chave = mapa[tecla]
			valor = 0
			if chave == "gols_pro":
				valor = it.get("gols_pro", it.get("golsPro", it.get("golspro", 0)))
				ui.message(f"{nome}: {nomes[tecla]} {valor}")
			elif chave == "gols_contra":
				valor = it.get("gols_contra", it.get("golsContra", it.get("golscontra", 0)))
				ui.message(f"{nome}: {nomes[tecla]} {valor}")
			elif chave == "aproveitamento":
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
					if jogos > 0:
						valor = (pontos / (jogos * 3.0)) * 100.0
					else:
						valor = 0.0
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
			else:
				valor = it.get(chave, 0)
				ui.message(f"{nome}: {nomes[tecla]} {valor}")
		else:
			event.Skip()


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

			for item, handler in (
				(self._toolsMenuItemOpen, self._on_tools_menu_open),
			):
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

	def _mostrar_erro(self, resumo: str, detalhes: str):
		try:
			resumo = (resumo or "").strip() or _("Ocorreu um erro.")
			detalhes = (detalhes or "").strip() or resumo

			ui.message(resumo)

			dlg = ErrorDetailsDialog(gui.mainFrame, resumo, detalhes)
			try:
				dlg.ShowModal()
			finally:
				dlg.Destroy()
		except Exception:
			log.exception("Falha ao exibir detalhes do erro")


	def _mostrar_erro_e_cache(self, resumo: str, detalhes: str, dados_cache, idade_segundos: float):
		"""Mostra detalhes do erro e, em seguida, abre a tabela com o cache."""
		try:
			mins = int(round((idade_segundos or 0) / 60.0))
			resumo2 = (resumo or "").strip() or _("Ocorreu um erro.")
			if mins <= 0:
				resumo2 = resumo2 + " " + _("Mostrando dados do cache.")
			else:
				resumo2 = resumo2 + " " + _("Mostrando dados do cache ({mins} min).").format(mins=mins)
			self._mostrar_erro(resumo2, detalhes)
			self._mostrar_tabela(dados_cache)
		except Exception:
			log.exception("Falha ao exibir erro e cache")
			try:
				self._mostrar_tabela(dados_cache)
			except Exception:
				pass

	def _mostrar_tabela(self, dados):
		try:
			TabelaDialog(dados, onTrocarChave=self._trocar_chave_api, onAbrirWidget=self._abrir_widget).ShowModal()
		except Exception:
			log.exception("Falha ao exibir diálogo de tabela")
	def _abrir_widget(self):
		try:
			ui.message(_("Abrindo no navegador."))
			webbrowser.open(WIDGET_URL)
		except Exception:
			log.exception("Falha ao abrir widget")
			ui.message(_("Não foi possível abrir o widget."))


	def _carregar_cache(self):
		cache = _read_json(CACHE_FILE)
		if not isinstance(cache, dict):
			return None
		timestamp = cache.get("timestamp")
		dados = cache.get("dados")
		if not isinstance(timestamp, (int, float)) or not isinstance(dados, list):
			return None
		if (time.time() - timestamp) >= CACHE_TTL_SECONDS:
			return None
		return dados


	def _carregar_cache_stale(self):
		"""Carrega o cache mesmo expirado. Retorna (dados, idadeSegundos) ou (None, None)."""
		cache = _read_json(CACHE_FILE)
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

	def _carregar_token(self):
		cfg = _read_settings()
		if cfg.get("use_free_key") is True:
			return FREE_API_KEY
		val = cfg.get("api_key")
		if isinstance(val, str) and val.strip():
			val = val.strip()
			try:
				if val.startswith("dpapi:"):
					return _dpapi_unprotect(val)
				return val
			except Exception:
				log.exception("Falha ao descriptografar token")
				return None
		return None

	def _salvar_token(self, token: str):
		try:
			token = (token or "").strip()
			if not token:
				return False
			protegido = _dpapi_protect(token)
			cfg = _read_settings()
			cfg["api_key"] = protegido
			cfg["use_free_key"] = False
			cfg["setup_done"] = True
			_write_settings(cfg)
			return True
		except Exception:
			log.exception("Falha ao salvar token")
			return False

	def _ativar_chave_gratis(self):
		try:
			cfg = _read_settings()
			cfg["use_free_key"] = True
			cfg["setup_done"] = True
			_write_settings(cfg)
			self._invalidar_cache()
			return True
		except Exception:
			log.exception("Falha ao ativar chave grátis")
			return False

	def _invalidar_cache(self):
		try:
			if os.path.isfile(CACHE_FILE):
				os.remove(CACHE_FILE)
		except Exception:
			pass


	def _prompt_chave_api(self, parent):
		dlg = ConfigDialog(parent)
		try:
			if dlg.ShowModal() != wx.ID_OK:
				return False
			chave = (dlg.txt_chave.GetValue() or "").strip()
			if not chave:
				return False
			if not self._salvar_token(chave):
				ui.message(_("Não foi possível salvar a chave."))
				return False
			self._invalidar_cache()
		finally:
			dlg.Destroy()

		msg = wx.MessageDialog(
			parent if parent else gui.mainFrame,
			_("Chave adicionada!"),
			_("API Futebol"),
			wx.OK | wx.ICON_INFORMATION
		)
		try:
			msg.ShowModal()
		finally:
			msg.Destroy()

		wx.CallAfter(lambda: self.script_tabela(None))
		return True



	def _trocar_chave_api(self, tabelaDlg):
		try:
			if tabelaDlg:
				try:
					tabelaDlg.Close()
				except Exception:
					pass
			parent = gui.mainFrame
			self._prompt_chave_api(parent)
		except Exception:
			log.exception("Falha ao trocar chave")


	def _salvar_cache(self, dados):
		try:
			_write_json_atomic(CACHE_FILE, {"timestamp": time.time(), "dados": dados})
		except Exception:
			log.exception("Falha ao salvar cache")

	def _buscar_tabela_em_thread(self, token: str):
		def worker():
			try:
				url = "https://api.api-futebol.com.br/v1/campeonatos/10/tabela"
				headers = {
					"Authorization": f"Bearer {token}",
					"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
					"Accept": "application/json",
					"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
				}
				req = urllib.request.Request(url, headers=headers)
				with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_SECONDS) as resp:
					payload = resp.read().decode("utf-8", errors="replace")
				dados = json.loads(payload)
				if not isinstance(dados, list):
					raise ValueError("Resposta inesperada da API")
				self._salvar_cache(dados)
				wx.CallAfter(lambda: self._mostrar_tabela(dados))
			except urllib.error.HTTPError as e:
				log.exception("HTTPError ao consultar API")
				code = getattr(e, "code", None)
				reason = getattr(e, "reason", "")
				detail = _extract_http_error_detail(e)
				if isinstance(detail, str):
					detail = detail.strip()

				snippet = ""
				if detail:
					snippet = detail.replace("\r", " ").replace("\n", " ").strip()
					if len(snippet) > 180:
						snippet = snippet[:180].rstrip() + "…"

				cloud = (detail or "").lower()
				if ("error 1010" in cloud) or (("1010" in cloud) and ("cloudflare" in cloud or "access denied" in cloud)):
					resumo = _("Bloqueado pelo Cloudflare (erro 1010). Tente outra rede (por exemplo, hotspot do celular) ou use \"Ver no navegador\".")
					detalhes = _("URL: {url}\nHTTP: {code}\nMotivo: {reason}\n\nResposta:\n{detail}\n").format(
						url=url, code=code or "", reason=reason or "", detail=detail or ""
					)
					dados_cache, idade = self._carregar_cache_stale()
					if dados_cache is not None:
						wx.CallAfter(lambda: self._mostrar_erro_e_cache(resumo, detalhes, dados_cache, idade))
					else:
						wx.CallAfter(lambda: self._mostrar_erro(resumo, detalhes))
					return

				if code == 401:
					resumo = _("Chave inválida ou expirada (erro 401). Se você estiver usando a chave grátis, ela pode ter atingido o limite. Use \"Trocar chave API\" ou \"Ver no navegador\".")
				elif code == 403:
					resumo = _("Acesso negado (erro 403). Se você estiver usando a chave grátis, ela pode ter atingido o limite ou sido bloqueada. Use \"Trocar chave API\" ou \"Ver no navegador\".")
				elif code == 429:
					resumo = _("Muitas requisições (erro 429). Se você estiver usando a chave grátis, ela pode ter atingido o limite. Tente novamente mais tarde ou use \"Trocar chave API\".")
				elif isinstance(code, int) and 500 <= code <= 599:
					resumo = _("A API está instável no momento. Tente novamente mais tarde.")
				else:
					resumo = _("Erro HTTP {code}.").format(code=code or "")

				if snippet:
					resumo = resumo + " " + snippet

				detalhes = _("URL: {url}\nHTTP: {code}\nMotivo: {reason}\n\nResposta:\n{detail}\n").format(
					url=url, code=code or "", reason=reason or "", detail=detail or ""
				)
				dados_cache, idade = self._carregar_cache_stale()
				if dados_cache is not None:
					wx.CallAfter(lambda: self._mostrar_erro_e_cache(resumo, detalhes, dados_cache, idade))
				else:
					wx.CallAfter(lambda: self._mostrar_erro(resumo, detalhes))
			except urllib.error.URLError as e:
				log.exception("URLError ao consultar API")
				reason = getattr(e, "reason", "")
				resumo = _("Sem conexão com a internet ou servidor inacessível.")
				if reason:
					s = str(reason).replace("\r", " ").replace("\n", " ").strip()
					if len(s) > 160:
						s = s[:160].rstrip() + "…"
					resumo = resumo + " " + s
				detalhes = _("URL: {url}\nErro: {err}\n").format(url=url, err=str(reason or e))
				dados_cache, idade = self._carregar_cache_stale()
				if dados_cache is not None:
					wx.CallAfter(lambda: self._mostrar_erro_e_cache(resumo, detalhes, dados_cache, idade))
				else:
					wx.CallAfter(lambda: self._mostrar_erro(resumo, detalhes))
			except Exception as e:
				log.exception("Erro ao consultar API")
				resumo = _("Erro ao buscar dados. Tente novamente.")
				detalhes = _("URL: {url}\nErro: {err}\n").format(url=url, err=repr(e))
				dados_cache, idade = self._carregar_cache_stale()
				if dados_cache is not None:
					wx.CallAfter(lambda: self._mostrar_erro_e_cache(resumo, detalhes, dados_cache, idade))
				else:
					wx.CallAfter(lambda: self._mostrar_erro(resumo, detalhes))
			finally:
				self._fetchInProgress = False
				self._stop_loading_timer()

		self._fetchInProgress = True
		self._start_loading_timer()
		t = threading.Thread(target=worker, name="TabelaBrasileiraoFetch", daemon=True)
		t.start()

	def script_tabela(self, gesture):
		"""Abrir a tabela do Brasileirão"""
		if self._fetchInProgress:
			ui.message(_("Aguarde, buscando dados na API Futebol."))
			return

		dados_cache = self._carregar_cache()
		if dados_cache is not None:
			tones.beep(440, 30)
			wx.CallAfter(lambda: self._mostrar_tabela(dados_cache))
			return

		token = self._carregar_token()
		if not token:
			cfg = _read_settings()
			if cfg.get("setup_done") is not True:
				def ask_first_run():
					dlg = wx.MessageDialog(
						gui.mainFrame,
						_("Deseja usar a chave grátis da API Futebol?"),
						_("API Futebol"),
						wx.YES_NO | wx.ICON_QUESTION
					)
					try:
						res = dlg.ShowModal()
					finally:
						dlg.Destroy()

					if res == wx.ID_YES:
						if self._ativar_chave_gratis():
							wx.CallAfter(lambda: self.script_tabela(None))
						else:
							ui.message(_("Não foi possível ativar a chave grátis."))
					else:
						wx.CallAfter(lambda: self._prompt_chave_api(gui.mainFrame))

				tones.beep(220, 200)
				wx.CallAfter(ask_first_run)
				return

			tones.beep(220, 200)
			ui.message(_("Configuração necessária."))
			wx.CallAfter(lambda: self._prompt_chave_api(gui.mainFrame))
			return

		tones.beep(880, 50)
		ui.message(_("Buscando dados na API Futebol."))
		self._buscar_tabela_em_thread(token)

	__gestures = {"kb:control+shift+t": "tabela"}
