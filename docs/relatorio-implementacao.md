# Relatório: adequação do Odisseu à tese ModiYacht

## 1. Objetivo
Aproximar o sistema da tese *Development of a CAD System for Parametric and Attribute-Based Modification of Yacht Hull Models* (Khan, ITU, 2017). A análise inicial mostrou que o S-TLBO e os atributos já existiam. O gerador do casco era outro: seções parabólicas com 6 parâmetros, enquanto a tese usa regiões com Bézier, patches de Coons e 28 parâmetros.

## 2. Diagnóstico inicial

| Item da tese | Situação antes |
|---|---|
| Regiões Entrada, Meio e Popa; curvas de Bézier; patches de Coons | Ausente |
| 28 parâmetros (Tabela 3.2) | Só 6 a 8 parâmetros |
| 14 operadores de forma (Grupos 1 e 2) com abordagem iterativa | Ausente |
| Quina dupla, espessura de quilha, cascos SD, P e D | Ausente |
| Hidrostática (Tabela 3.6) | Ausente |
| Inspeção de fairness (zebra, seções, curvatura) | Ausente |
| S-TLBO conforme a equação 4.15 | Parcial: custo simplificado e sem U₂/U₃ |
| Atributos sobre as 11 variáveis da Tabela 4.1 | Parcial: usava outras variáveis |
| Interface da Figura 5.3 (Grupos 1 e 2) e da Figura 5.8 (atributos) | Parcial |

## 3. O que foi implementado

**Modelo paramétrico**
- `bezier.py`: Bézier cúbica, curvatura, raio mínimo e abordagem iterativa (F, ξ=1000, µ=15). Também resolve o raio mínimo de curvatura e o seu máximo alcançável.
- `hull_model.py`: regiões, estações, curvas características, patches de Coons espelhados e medição dos 28 parâmetros.
- `hull_types.py`: cascos iniciais SD, P e D. O SD reproduz a Tabela 3.4 inteira.
- `mesh.py`: malha com fusão de vértices.

**Operadores de forma** (`shape_operators.py`)
- Grupo 1: alongamento, alargamento, aprofundamento, posição e espessura da quina, inserir/remover quina, espessura da quilha, altura da roda de proa e ângulos de proa, entrada e tosamento.
- Grupo 2: raio mínimo e concavidade das estações.
- Preservam G0/G1 nas estações (desvio medido: 0°). Cada um leva menos de 1 s; a tese cita menos de 4 s.
- Raio inalcançável gera aviso com o limite máximo da curva, como na Figura 5.5.

**Hidrostática** (`hydrostatics.py`)
- Todas as colunas da Tabela 3.6, para três calados, com exportação em CSV.
- Validada contra uma caixa com solução exata.

**Amostragem e atributos** (`sampling.py`, `attributes.py`, `workers.py`)
- S-TLBO conforme o capítulo 4:
  - custo U₁ + αU₂ + βU₃ (α=100, β=1000);
  - seleção gulosa de professores;
  - critério de parada;
  - restrições dos 3 participantes (Tabela 4.1).
- Executa em segundo plano, com progresso e cancelamento.
- 10 atributos sobre as 11 variáveis da Tabela 4.1.

**Interface**
- `parameter_panel.py`: diálogos do Grupo 1 e do Grupo 2; só os campos alterados são aplicados.
- `attribute_panel.py`, `hydrostatic_panel.py`, `curvature_dialog.py`.
- Menu Visualizar com zebra, seções, curvas características, polígonos de controle e gráfico de curvatura.
- Janela principal com botões SD, P e D.

## 4. Verificação
- 180 testes automatizados passando (o conjunto antigo tinha 45).
- Cobertura nova:
  - Bézier e IA;
  - cada operador (valor atingido, parâmetros vizinhos intocados, G1, malha fechada);
  - hidrostática;
  - S-TLBO;
  - atributos.
- Teste de fumaça da janela em modo offscreen: fluxo completo sem erros.
- A suíte leva cerca de 80 segundos.

## 5. Diferenças deliberadas em relação à tese
1. **Atributos:** os coeficientes de Dogan estão truncados na Figura 5.6. Usei um modelo substituto com a mesma estrutura e o mesmo limiar de 0,5.
2. **Similaridade F:** os trechos retos (κ ≈ 0) recebem raio-limite R_cap = 100/max(κ) em vez de R = ∞; a métrica usa raios conforme a equação 3.3 da tese.
3. **Penalidade do S-TLBO:** a contagem de restrições violadas ganhou um termo pequeno de desempate pelo grau da violação.
4. **Parada do S-TLBO:** a paciência é maior que as duas iterações da tese, por causa das penalidades discretas.
5. **Colapso:** a busca principal deixava cerca de 18 de 30 projetos em colapso; uma etapa final de reparo zera o colapso (N = 30, sem restrições) com U₁ ≈ 233–242, contra 241,78 na tese. Com atributos muito restritivos o colapso pode permanecer.
6. **Tabela 4.1:** o "110 ≤ β ≤ 80" do participante 3 é impossível, então li como 80 ≤ β ≤ 120.
7. **Eixos:** x é o comprimento, y a boca e z a vertical; a tese usa Z no comprimento.
8. **Espessuras:** as de quina e de quilha são derivadas de uma curva central e variam suavemente entre as estações.

## 6. Segunda rodada: lacunas fechadas

Depois do primeiro relatório ficaram sete pontos em aberto. Situação de cada um:

| Ponto | Resultado |
|---|---|
| Hidrostática sem comparação com a Tabela 3.6 | Comparada. O casco SD foi calibrado (busca em paralelo sobre os ângulos das tangentes) e ficou com erro mediano de 4,3 % (máximo 11 %) contra a tabela. Operadores validados sem entrar no ajuste: quilha K = 0,5 m (3,0 % / 11 %), alongamento Lₘ + 3 m (3,6 % / 11 %), alargamento Bₑ + 1 m (7,4 % / 28 %) |
| Convenção do KB | A tabela da tese traz KB ≈ T/3, coerente só se for contado da linha d'água. O Odisseu mede da quilha (padrão naval); a conversão é `T − KB`, documentada no código e no README |
| Colapso no S-TLBO (18 de 30) | Etapa de reparo ao final da busca. Com N = 30 e sem restrições: colapso 0 e U₁ = 233–242 (tese: 241,78) |
| Coeficientes de Dogan | **Não recuperáveis.** A Figura 5.6 é uma imagem de 1096 × 519 px, com linhas intermediárias omitidas. O modelo substituto continua, mas agora os coeficientes reais podem ser carregados de `app/data/attribute_models.json` (modelo de partida em `docs/attribute_models.template.json`) |
| Interface só vista offscreen | Conferida na janela real do Windows, com fontes e vista 3D: painéis, sobreposições, hidrostática, operadores, atributos (10 projetos amostrados em 13 s), gráfico de curvatura. As listras de zebra saíam em blocos; passaram a ser traçadas por pixel |
| Sequências da Figura 3.16 | As duas rodam e estão nos testes. Descobri e corrigi um erro que desfazia a troca de ordem entre Fb e H (a troca era um no-op); a mesma correção cobre pontal × quina |
| Testes lentos (≈ 260 s) | 152 testes em 79 s. Além de reduzir populações, a construção do casco caiu de 5,5 s para 0,17 s (busca de curvatura máxima em duas etapas e varredura grossa da família de raios, com a mesma resolução ξ = 10 000) |
Limites que permanecem:
- A tese não informa a forma do casco entre as estações; a calibração casa a tabela em ordem de grandeza, não valor a valor. As maiores diferenças estão na concavidade (máx. 45 %) e no aprofundamento de Dₑ − 0,46 m (máx. 52 %; o texto da tese fala em "Dm" numa linha "on ER", então o operador pode ser outro).
- Com atributos muito estreitos (por exemplo cute + aesthetic, 0,1 % do espaço) o colapso não pode ser zerado: os níveis cobrem o espaço inteiro e a região viável não alcança todos.
- Na Figura 3.16(a), De = 2,5 m coincide com Fₑ = 2,5 m da Tabela 3.4; as quinas descem junto (1,5 / 1,5 / 0,9 m).

## 7. Riscos e pendências

- **Arquivos reescritos:** seis arquivos que tinham alterações não commitadas foram reescritos por cima (`main_window.py`, `parameter_panel.py`, `attribute_panel.py`, `hull_controller.py`, `attributes.py`, `sampling.py`), e `hull_generator.py`, `profiles.py`, `constraints.py` e `tests/test_hull_geometry.py` foram removidos. As versões *commitadas* anteriores continuam no histórico git; as alterações não commitadas daquele momento só existem no histórico de versões do OneDrive.
- **Atributos:** sem os coeficientes originais de Dogan, os atributos amostrados não coincidem com os da tese. Há como carregá-los (seção 6).
- **Forma entre as estações:** o casco SD reproduz a Tabela 3.4 exatamente e a Tabela 3.6 em ordem de grandeza (seção 6); não há como saber mais sem o modelo original da tese.
- **Documentação:** o `README.md` tem a tabela de correspondência com a tese e a validação contra a Tabela 3.6.

## 8. Terceira rodada: lacunas fechadas

| Ponto | Resultado |
|---|---|
| Similaridade F usa curvatura em vez do raio (equação 3.3) | Corrigida: F agora usa R = 1/κ com R_cap = 100/max(κ) para trechos retos. O cosseno é idêntico para curvas proporcionais. Aprimorada na quarta rodada com cosseno centrado (seção 9). |
| Operador de aprofundamento: De ou Dm? | Confirmado que De (entrada) é correto. O teste `DeepeningOperatorTests` verifica que reduzir De desloca o LCB para a ré (menos volume de proa) e que aumentar De o avança. O erro máximo de 52 % na coluna IT é irreduível sem o modelo original da tese. |
| Cascos P e D não tinham validação de consistência física | Adicionada a classe `PlaningDisplacementHullTests`: volumes crescentes, KB < T, KM = KB + BM, coeficientes em (0,1] e Cb ≈ Cp·Cm para ambos os tipos. |
| Exportação NURBS (.3dm) ausente | Novo módulo `app/models/rhino_export.py` converte cada Bézier cúbica em NurbsCurve exata (grau 3, nós [0,0,0,1,1,1]) e exporta convés, quilha, quina, estações e proa em camadas. O menu **Arquivo > Exportar casco como .3dm** chama o exportador; bombordo é espelhado. Requer `rhino3dm ≥ 8.0`. |
| Colapso do S-TLBO sem diagnóstico | `SamplingResult.collapse` registra os pares ainda em colapso após o reparo. Se collapse > 0, `warnings.warn` orienta o usuário a relaxar os atributos ou aumentar N. |

## 9. Quarta rodada: lacunas fechadas

| Ponto | Resultado |
|---|---|
| Similaridade F: trechos retos dominavam o cosseno | Cosseno centrado: subtrai a média de R antes do produto interno. Cantos agudos (R << média) ganham peso proporcional ao desvio; F = 1 preservado para curvas proporcionais. Res2 no casco de quina reta caiu de 0,46 para 0,013. Fallback para cosseno não centrado quando a distribuição de referência é uniforme. |
| Testes unitários de `rhino_export` ausentes | Novo arquivo `tests/test_rhino_export.py` com 17 testes: grau/nós/coordenadas da NurbsCurve, espelhamento _mirror_y (y negado, x/z inalterados), 5 camadas com nomes corretos, 25 curvas totais, contagens por camada (6 quina, 12 estações, 1 proa), grau 3 em todas, require_rhino3dm sem exceção com biblioteca instalada. |
| Testes de `SamplingResult.collapse` ausentes | 4 novos testes em `test_sampling.py`: tipo int, zero após reparo bem-sucedido (N=30), igualdade com `collapse_penalty()` sem reparo e ausência de UserWarning no caso normal. |
| Total de testes | 180 (eram 163 após a terceira rodada). |

## 10. Lacuna remanescente: modelos GMDH reais de Dogan

### Situação atual

O único item funcional ainda não implementado conforme a tese são os coeficientes originais dos modelos matemáticos de atributos (Figura 5.6, Dogan 2017). O código atual usa um **modelo substituto** — um único polinômio por atributo sobre as 11 variáveis padronizadas da Tabela 4.1, calibrado para que cada atributo e as combinações usuais sejam alcançáveis. Os valores de saída diferem dos de Dogan.

A referência original é: Doğan, K. M. e Günpınar, E., *Learning Yacht Hull Adjectives and Their Relationship with Hull Surface Geometry Using GMDH-Type Neural Networks for Human Oriented Smart Design*, Ocean Engineering, v. 145, pp. 215–229, 2017. DOI: 10.1016/j.oceaneng.2017.08.056. O artigo possui material suplementar ("Mathematical Models") no ResearchGate que contém as equações completas.

### Estrutura dos modelos reais

Os modelos de Dogan são redes GMDH em cascata: cada atributo Yⁱ é calculado por uma cadeia de neurônios intermediários N2, N3, …, N_k, onde cada neurônio combina dois termos — que podem ser variáveis de entrada ou a saída do neurônio seguinte:

```
N_k = a₀ + a₁·V₁ + a₂·V₂ + a₃·V₁·V₂
```

Os termos V₁ e V₂ podem ser a variável direta, sua raiz cúbica (`cubert`) ou a saída de N_{k+1}. O `AttributeModel` atual representa apenas um único neurônio; implementar os modelos reais requer uma classe de cascata.

### Cobertura da transcrição disponível (Figura 5.6)

| Atributo | Equações visíveis na figura | Implementável com os dados atuais |
|---|---|---|
| Strong | Completo: Y¹ e N2–N11 | Sim, se o mapeamento de variáveis for confirmado |
| Comfortable | Completo: Y³ e N2–N12 | Sim |
| Modern | Completo: Y⁸ e N2–N11 | Sim |
| Cute | Completo: Y¹⁰ e N2–N11 | Sim |
| Speedy | Parcial: Y², N2–N5 e N31–N33 | Não — faltam N6–N30 |
| Aesthetic | Parcial: Y⁴, N2–N5 e N31–N33 | Não — faltam N6–N30 |
| Usual | Parcial: Y⁵, N2–N5 e N11–N14 | Não — faltam N6–N10 |
| Aggressive | Parcial: Y⁶, N2–N5 e N13–N15 | Não — faltam N6–N12 |
| Compact | Parcial: Y⁷, N2, N4–N7, N27–N29 | Não — faltam vários nós intermediários |
| Charismatic | Parcial: Y⁹, N2–N5 e N31–N33 | Não — faltam N6–N30 |

### Problema de mapeamento de variáveis

Os modelos usam nomes que não correspondem diretamente às 11 variáveis atuais (`Le, Lm, Lr, Be, Bm, Br, De, Dm, Dr, beta, theta`):

| Nome em Dogan | Hipótese mais provável | Presente no espaço atual |
|---|---|---|
| `De_2`, `Dm_1`, `Dm_2`, `Dr_1` | Razões adimensionais (p. ex. De/Be, Dm/Lm) | Não como variável direta |
| `Re_1`, `Rm_1`, `Rr_1`, `Rr_0` | Raios de curvatura das estações (Rek, Rms, Rrs) | Não — excluídos do espaço de amostragem |
| `a`, `a1` | Ângulo de tosamento α (≈ `beta`) ou variante | Parcialmente |
| `R5`, `H` | Raio de estação específico; altura da roda de proa | Não como variável de projeto |

Os parâmetros de raio (`Re_1`, `Rm_1`, `Rr_1`) estão fora do `DESIGN_VARIABLES` atual. Inclui-los ampliaria o espaço de 11 para até 14–15 dimensões, com impacto no S-TLBO e em todo o fluxo de amostragem.

### O que é preciso para implementar

1. **Material suplementar de Dogan 2017** — fornece as equações intermediárias ausentes para os seis atributos parciais e confirma a convenção de normalização das variáveis.
2. **Mapeamento confirmado** — relacionar `De_2`, `Rm_1`, `a` etc. às variáveis do modelo; sem isso, implementar a transcrição com mapeamento errado produz resultados piores que o substituto.
3. **Extensão da arquitetura** — adicionar `CascadedAttributeModel` ou equivalente ao `attributes.py` para suportar cadeias de neurônios; o JSON de coeficientes em `app/data/attribute_models.json` precisaria de novo esquema.
4. **Decisão sobre o espaço de projeto** — incluir ou não os parâmetros de raio no `DESIGN_VARIABLES`; se incluídos, recalibrar `YACHT_HULL_SPACE` e retestar o S-TLBO.

Enquanto o material suplementar não estiver disponível, o substituto permanece funcional para uso qualitativo.
