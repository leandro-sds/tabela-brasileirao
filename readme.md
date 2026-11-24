# Tabela Brasileirão

**Autor:** Leandro Souza

---

## ⚽ O que é

O **Tabela Brasileirão** é um complemento para o NVDA que permite consultar, com acessibilidade, a **classificação do Brasileirão Série A e Série B**.

Os dados são obtidos do site do desenvolvedor, **www.leandross.com.br**, que mantém a classificação atualizada automaticamente.

---

## ✅ Como usar

### Abrir a tabela
- Atalho padrão: **Control + Shift + T** (abre a Série A)

### Alternar entre Série A e Série B
Dentro da janela da tabela, use os botões **Tabela Série A** ou **Tabela Série B** para alternar entre as séries.

### Atualizar a tabela
Use o botão **Atualizar tabela** para buscar a classificação do momento, direto da fonte. É o que usar durante os jogos, quando a classificação muda a cada resultado.

A busca leva alguns segundos e o NVDA emite bipes curtos enquanto isso. Ao terminar, o NVDA anuncia *"Tabela atualizada agora, direto da fonte"*.

Se a fonte não responder, o complemento usa o servidor automaticamente e anuncia *"Tabela atualizada"*.

E se o campeonato estiver entre temporadas ou em fase de playoff, quando não existe classificação para atualizar, o anúncio é *"Esta série ainda não tem classificação nova. Mostrando os últimos dados"*. Isso não é erro: é o campeonato que não tem números novos.

Em nenhum desses casos a janela fecha ou a tabela fica vazia.

Depois de atualizar, a lista volta no time que você tinha selecionado, mesmo que ele tenha mudado de posição — útil para acompanhar um time durante a rodada.

---

## ⌨️ Atalhos dentro da tabela

Na lista de classificação, você pode pressionar:

- **Setas para cima/baixo**: navega na lista (com bips ao chegar no início/fim)
- **F1**: abre a ajuda com os atalhos
- **V**: Vitórias
- **E**: Empates
- **D**: Derrotas
- **S**: Saldo de gols
- **J**: Jogos
- **P**: Gols pró
- **C**: Gols contra
- **A**: Aproveitamento
- **Ctrl+C**: copia a linha selecionada
- **Ctrl+A**: copia a tabela inteira
- **Ctrl+S**: salva a tabela em TXT
- **Esc**: fecha a janela

---

## 💾 Cache (mais rápido e economiza dados)

Ao abrir, o complemento usa cache de **30 minutos** para responder na hora e gastar menos internet. Quando você quer o número do momento, use o botão **Atualizar tabela**: ele ignora o cache e vai direto na fonte.

---

## ⚙️ Personalizar o atalho

Você pode alterar o atalho em:

**Menu NVDA → Preferências → Definir comandos → Tabela Brasileirão**

---

## 🏁 Fim de temporada

Quando uma série encerra a fase de pontos corridos, a tabela de classificação sai do ar na fonte e o complemento passa a mostrar a **classificação final** daquela temporada. O botão **Atualizar tabela** continua funcionando; ele apenas não encontra números novos até o campeonato seguinte começar.
