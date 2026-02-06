# Tabela Brasileirão

**Autor:** Leandro Souza

---

## ⚽ Descrição

O **Tabela Brasileirão** é um complemento para o NVDA que permite acompanhar a **classificação do Brasileirão Série A** com rapidez e acessibilidade.

Os dados são obtidos através da **API Futebol**.

---

## ✅ Recursos

- Atalho para abrir a tabela (**configurável** em *Preferências → Definir comandos*).
- Lista acessível, com bips ao chegar no início/fim.
- Atalhos rápidos dentro da tabela:
  - **V** = Vitórias
  - **E** = Empates
  - **D** = Derrotas
  - **S** = Saldo de gols
  - **J** = Jogos
  - **P** = Gols pró
  - **C** = Gols contra
- **Cache inteligente de 30 minutos** (economiza dados e abre mais rápido).
- Botão **Trocar chave API** para colar uma nova chave, quando necessário.
- Botão **Ver no navegador** para abrir uma visualização web no navegador padrão.

---

## ⌨️ Atalho para abrir a tabela

- Atalho padrão: **Control + Shift + T**

### Personalizar o atalho

Você pode alterar o atalho em:

**Menu NVDA → Preferências → Definir comandos → Tabela Brasileirão**

---

## 🔑 Sobre a chave da API (importante)

Este add-on consulta dados da **API Futebol** (api-futebol.com.br).

### Opção 1: usar a chave grátis que vem no add-on

Na primeira vez que você abrir o complemento, ele pergunta:

**“Deseja usar a chave grátis da API Futebol?”**

- Se você escolher **Sim**, o add-on usa a chave que já vem com ele.
- Essa chave é **limitada** e pode ter restrições (por exemplo: limite de requisições, bloqueios temporários ou instabilidade em horários de pico).

> Em outras palavras: funciona, mas pode falhar em alguns momentos por ser uma chave compartilhada/limitada.

### Opção 2: criar sua própria chave

Você pode criar sua própria chave em **api-futebol.com.br**.

- A conta na API Futebol é **paga**.
- Com sua chave própria, você tende a ter mais estabilidade e controle (dependendo do plano).

---

## 🔁 Como trocar a chave

1. Abra a tabela.
2. Clique em **Trocar chave API**.
3. Cole sua nova chave e confirme.
4. O complemento exibirá **“Chave adicionada!”** e carregará a tabela automaticamente.

---

## 🧩 Problemas comuns

### Erro 1010 (Cloudflare / bloqueio de rede)

Em algumas redes (por exemplo, redes corporativas/órgãos públicos), o acesso pode ser bloqueado por regras de segurança.

Se isso acontecer:
- teste em outra internet (por exemplo, **hotspot do celular**);
- peça ao TI para liberar o acesso;
- use o botão **Ver no navegador**.

---
