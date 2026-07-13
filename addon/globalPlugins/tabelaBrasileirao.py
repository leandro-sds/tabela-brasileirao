import globalPluginHandler
import ui
import urllib.request
import json
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

REMOTE_JSON_URL_A = "https://www.wpacessivel.com.br/tabela/cache_tabela_A.json"
REMOTE_JSON_URL_B = "https://www.wpacessivel.com.br/tabela/cache_tabela_B.json"


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

	def _atualizar_dados_na_tela(self, novos_dados):
		self.dados = novos_dados or []
		self._popular_lista()
		self._ajustar_largura_coluna()

		if self.lista.GetItemCount() > 0:
			self.lista.SetFocus()
			self.lista.SetItemState(0, wx.LIST_STATE_SELECTED, wx.LIST_STATE_SELECTED)
			self.lista.EnsureVisible(0)

	def _set_atualizando(self, updating: bool):
		try:
			self.btnAtualizar.Enable(not updating)
			self.btnFechar.Enable(not updating)
			if updating:
				self.btnAtualizar.SetLabel(_("Atualizando..."))
			else:
				self.btnAtualizar.SetLabel(_("Atualizar agora"))
		except Exception:
			pass

	def _on_click_atualizar(self, event):
		if not callable(self._onForceRefresh):
			return

		self._set_atualizando(True)
		tones.beep(880, 60)
		ui.message(_("Atualizando dados da tabela..."))

		def ok(novos_dados):
			self._set_atualizando(False)
			self._atualizar_dados_na_tela(novos_dados)
			tones.beep(660, 40)
			ui.message(_("Tabela atualizada."))

		def fail():
			self._set_atualizando(False)
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
			"""Atalhos disponíveis:

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
		try:
			if wx.TheClipboard.Open():
				try:
					wx.TheClipboard.SetData(wx.TextDataObject(texto))
					wx.TheClipboard.Flush()
				finally:
					wx.TheClipboard.Close()
			ui.message(_("Copiado: {linha}").format(linha=texto))
		except Exception:
			ui.message(_("Não foi possível copiar."))

	def _copiar_tabela_para_area_de_transferencia(self):
		texto = self._gerar_texto_tabela_simples()
		try:
			if wx.TheClipboard.Open():
				try:
					wx.TheClipboard.SetData(wx.TextDataObject(texto))
					wx.TheClipboard.Flush()
				finally:
					wx.TheClipboard.Close()
			ui.message(_("Tabela copiada."))
		except Exception:
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
		if self._fetchInProgress:
			ui.message(_("Aguarde, já estou buscando dados."))
			fail()
			return
		self._baixar_json_em_thread(serie, ok, fail)

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
