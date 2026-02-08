# -*- coding: UTF-8 -*-

def _(arg):
	return arg

addon_info = {
	"addon_name": "tabelaBrasileirao",
	"addon_summary": _("Tabela do Brasileirão"),
	"addon_description": _("""Mostra a classificação do Brasileirão Série A no NVDA.
Atalhos na tabela: V/E/D/S/J/P/C.
Pode usar a chave grátis (limitada) do add-on ou informar uma chave própria da API Futebol."""),
	"addon_version": "2026.2.08",
	"addon_author": "Leandro Souza",
	"addon_url": "https://github.com/leandro-sds/tabela-brasileirao/",
	"addon_docFileName": "readme.md",
	"addon_minimumNVDAVersion": "2024.1.0",
	"addon_lastTestedNVDAVersion": "2025.3.2",
	"addon_updateChannel": "stable",
	"addon_license": "GPL 2",
	"addon_licenseURL": "https://www.gnu.org/licenses/gpl-2.0.html",
}

pythonSources = [
	"addon/globalPlugins/tabelaBrasileirao.py",
]

i18nSources = pythonSources + ["buildVars.py"]
excludedFiles = []
baseLanguage = "pt_BR"
markdownExtensions = []
brailleTables = {}
symbolDictionaries = {}
