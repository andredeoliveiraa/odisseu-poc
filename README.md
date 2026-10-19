# Odisseu

Odisseu é um protótipo desktop para modelagem **paramétrica** e **por atributos**
de cascos de iates, seguindo a tese *Development of a CAD System for Parametric
and Attribute-Based Modification of Yacht Hull Models* (S. Khan, ITU, 2017 — o
sistema **ModiYacht**). A correspondência com a tese está resumida na tabela do
fim deste arquivo.

## Como executar

```powershell
pip install -r requirements.txt
python main.py
```

## Modelo paramétrico (capítulo 3)

O casco é dividido em **três regiões** — entrada, meio e popa — separadas pelas
estações 1, 2 e 3. Cada região é formada por *curvas características* (Bézier
cúbicas): linha de convés, linha(s) de quina, linha de quilha e linhas de
estação (superior e inferior); a proa tem ainda a linha de roda de proa. A
superfície vem de **patches de Coons** entre essas curvas, espelhados em torno
do plano de simetria. A espessura da quina (casco de quina dupla) e a da quilha
(painel plano) completam o modelo.

Os **28 parâmetros** da Tabela 3.2 são medidos no casco e editáveis no painel
lateral: comprimentos `Lₑ Lₘ Lᵣ`, bocas `Bₑ Bₘ Bᵣ`, pontais `Dₑ Dₘ Dᵣ`, posição
das quinas `Fₑ Fₘ Fᵣ F_b`, espessuras de quina `Cₑ Cₘ Cᵣ`, raios mínimos de
curvatura `Rₑₖ Rₑₛ₁ Rₑₛ₂ Rₘₛ₁ Rₘₛ₂ Rᵣₛ₁ Rᵣₛ₂`, roda de proa `H`, quilha `K` e os
ângulos de proa `β`, de tosamento `α` e de entrada `θ`.

Há três **cascos iniciais** — semi-deslocamento (SD, com os valores da Tabela
3.4), planeio (P) e deslocamento (D) — na barra superior e no menu **Casco
inicial**. Dos três é possível chegar a qualquer outro tipo com sequências de
operadores (Figura 3.16): as duas sequências da figura (casco de quina dupla com
fundo em V raso e casco redondo) rodam e estão nos testes. Na (b) valem os
valores da tese; na (a) a quina desce junto com o pontal (F = 1,5 / 1,5 / 0,9 m),
porque a tese dá De = 2,5 m, igual ao Fₑ da Tabela 3.4.
Cada operador leva menos de 0,4 s (a tese informa menos de 4 s), e a construção
de um casco inicial, cerca de 0,2 s.

### Operadores de forma

No painel **Parâmetros do casco**, altere os campos desejados e use **Aplicar
operadores** (`Ctrl+Enter`, ou `Enter` num campo). Só os campos alterados são
aplicados; sem alterações o casco não muda.

* **Grupo 1** (abordagem iterativa): alongamento, alargamento, aprofundamento,
  posição e espessura da quina, inserção/remoção de quina (dupla, simples, sem
  quina), espessura da quilha, comprimento vertical da roda de proa e ângulos de
  proa, de entrada e de tosamento.
* **Grupo 2**: raio mínimo de curvatura (das linhas de estação e da quilha na
  entrada) e concavidade das linhas de estação (côncava/convexa). Um raio acima
  do máximo alcançável é recusado com o limite da curva. Raio `0` deixa a linha
  praticamente reta; "reta (∞)" indica que a linha já é reta.

Cada operador respeita os três critérios da tese: **continuidade G0/G1** entre
regiões, **fairness** (a **abordagem iterativa** reposiciona `P1` e `P2` das
curvas que se movem para maximizar a similaridade `F` entre as distribuições de
curvatura da curva de entrada e da modificada, com ξ = 1000 e µ = 15) e
**modificação independente** dos parâmetros.

A curvatura é comparada por `κ = 1/R` e não pelo raio `R` (como escreve a tese):
o cosseno é o mesmo em intenção, mas evita o `R → ∞` dos trechos retos.

### Inspeção de qualidade (Figuras 3.14 e 3.15)

No menu **Visualizar**: *listras de zebra*, *curvas de seção*, *curvas
características*, *polígonos de controle* e **Gráfico de curvatura...**, que
compara a curvatura de convés, quina e quilha antes e depois dos operadores
(com o valor de `F`) e informa o desvio angular G1 nas estações.

### Hidrostática (Tabela 3.6)

A aba **Hidrostática** calcula, para três calados medidos a partir da linha de
base (por padrão 0,74, 1,24 e 1,74 m no casco SD, como na tese): `LWL, BWL, V,
Aw, LCB, KB, LCF, IL, IT, Aₓ, BM, KM, Cp, Cm, Cw, Cb`. O volume e os momentos
saem do teorema da divergência sobre a malha cortada na linha d'água (o espelho
de popa é tampado); `LCB` e `LCF` são medidos a partir do espelho. A tabela pode
ser exportada em CSV.

`KB` e `KM` são medidos a partir da quilha, como é padrão em arquitetura naval
(`KM = KB + BM`). A Tabela 3.6 da tese traz `KB ≈ T/3`, que só é coerente se for
contado a partir da linha d'água (`T − KB`); ao comparar com a tabela, converta.

**Validação contra a Tabela 3.6.** O casco SD inicial foi ajustado (ângulos das
tangentes em `app/models/hull_types.py`) para reproduzir, ao mesmo tempo, os 28
parâmetros da Tabela 3.4, a hidrostática do casco de entrada da Tabela 3.6 e o
alcance dos raios da Figura 3.16(b). Erro relativo dos 48 valores (16 colunas,
3 calados) de cada linha da tabela, com os operadores aplicados ao casco SD:

| Linha da Tabela 3.6 | Erro mediano | Erro máximo |
| --- | --- | --- |
| Casco de entrada | 4,3 % | 11 % |
| Espessura da quilha, K = 0,5 m | 3,0 % | 11 % |
| Alongamento Lₘ + 3 m | 3,6 % | 11 % |
| Alargamento Bₑ + 1 m | 7,4 % | 28 % |
| Concavidade da linha inferior da estação 1 | 4,8 % | 45 % |
| Aprofundamento Dₑ − 0,46 m | 7,6 % | 52 % |

Só a primeira linha e a concavidade entraram no ajuste; as demais são validação
independente. A tese não diz quais parâmetros do casco SD originais definem a
forma entre as estações, então a coincidência é de ordem de grandeza, não exata
(`tests/test_hydrostatics.py::ThesisTableTests`).

## Modelagem por atributos (capítulos 4 e 5)

A aba **Atributos** segue as Figuras 5.6 a 5.8:

* Cada um dos 10 atributos (Strong, Speedy, Comfortable, Aesthetic, Usual,
  Aggressive, Compact, Modern, Charismatic, Cute) é avaliado por um polinômio no
  formato GMDH (termos lineares, `cubert`, quadráticos e produtos) sobre as 11
  variáveis **padronizadas** da Tabela 4.1. O casco expressa o atributo quando o
  valor é maior que 0,5; a avaliação acompanha o casco atual.
* **Amostrar projetos** executa o **S-TLBO** em segundo plano (com progresso e
  cancelamento) para `N` cascos que satisfazem todos os atributos escolhidos.
  O custo é `Ū(T) = U₁ + α·U₂ + β·U₃` (equação 4.15): energia potencial de
  Audze-Eglais (*space-filling*), penalidade de colapso (hipercubo latino) e
  penalidade estática por restrição violada, com α = 100 e β = 1000. Os
  professores iniciais são escolhidos de forma gulosa e a busca para quando o
  custo estabiliza. Depois da busca, uma etapa de reparo move cada coordenada
  que colide com outra para um nível livre do mesmo eixo, só quando o custo `Ū`
  diminui; com isso N = 30 projetos saem **sem colapso** (U₂ = 0) e com
  U₁ ≈ 235–245, como os 241,78 da tese. Com restrições de atributo muito
  estreitas o colapso pode permanecer: os níveis cobrem o espaço inteiro e a
  região viável pode não alcançar todos eles.
* Opcionalmente, as **preferências** de um dos três participantes da Tabela 4.1
  entram como restrições geométricas (amostragem *customer-centered*).
* O controle deslizante e **Desenhar** exibem o projeto escolhido.

Os coeficientes de Dogan aparecem truncados na Figura 5.6 (a imagem do PDF tem só
1096 × 519 pixels, com linhas intermediárias omitidas) e dependem de curvas do
ModiYacht que não existem aqui. `app/models/attributes.py` usa, portanto, um
**modelo substituto** com a mesma estrutura, padronização e limiar, calibrado
para que cada atributo e as combinações usuais sejam alcançáveis (por exemplo,
compacto + moderno + rápido, como na Figura 5.9).

Para usar coeficientes reais, grave-os em `app/data/attribute_models.json` (lido
na inicialização) ou chame `load_attribute_models(caminho)`. O formato é o de
[docs/attribute_models.template.json](docs/attribute_models.template.json), que
traz o modelo substituto atual como ponto de partida: cada atributo tem
`intercept`, `linear`, `cube_root`, `quadratic` e `interaction` sobre as 11
variáveis padronizadas.

## Outros recursos

- Importe malhas STL, OBJ, PLY, VTK, VTP ou arquivos **.3dm do Rhino** pelo
  menu **Arquivo > Abrir casco** ou arrastando o arquivo para a janela. Do
  Rhino só entram superfícies com malha de exibição já salva no arquivo, e
  imagens de referência coladas na cena (comando "Picture") são ignoradas. A
  unidade do .3dm é mostrada no painel e na grade cotada. A pasta `exemplos/`
  traz um STL para experimentar.
- Desloque, rotacione ou redimensione o modelo inteiro em **Transformar
  objeto**; `Ctrl+Z` e `Ctrl+Y` desfazem e refazem (20 operações).
- Exporte o modelo visível em STL, PLY, VTK ou VTP. **Fechar convés** (em
  *Modelo atual*) gera uma malha estanque, necessária para volume, CFD ou
  impressão 3D.
- **Arquivo > Editar superfície NURBS...** abre um .3dm e permite arrastar os
  pontos de controle de uma superfície na cena 3D. **Concluir edição de
  superfície** mantém o resultado e **Salvar superfície como .3dm...** exporta
  só a superfície editada, na mesma unidade do original.
- Mouse: orbitar, deslocar e aproximar. `F` enquadra o modelo e `Home` volta à
  vista isométrica.

## Correspondência com a tese

| Tese | Implementação |
| --- | --- |
| 3.2 Regiões, curvas características, patches de Coons | `app/models/hull_model.py` |
| 3.2.3 Cascos iniciais (planeio, semi-deslocamento, deslocamento) | `app/models/hull_types.py` |
| 3.3.1–3.3.2 Critérios de qualidade, abordagem iterativa (`F`, ξ, µ) | `app/models/bezier.py` |
| 3.3.2–3.3.3 Operadores de forma (Grupos 1 e 2) | `app/models/shape_operators.py` |
| 3.4 Fairness (zebra, seções, curvatura), hidrostática | `app/visualization.py`, `app/views/curvature_dialog.py`, `app/models/hydrostatics.py` |
| 4.2–4.3 TLBO e S-TLBO (restrito e irrestrito) | `app/models/sampling.py` |
| 4.4 Espaços de projeto e restrições (Tabelas 4.1 e 4.2) | `app/models/sampling.py` |
| 5.1 Modelagem paramétrica (diálogos Grupo 1 e 2) | `app/views/parameter_panel.py` |
| 5.2 Modelagem por atributos (Figuras 5.6–5.8) | `app/models/attributes.py`, `app/views/attribute_panel.py` |

Diferenças deliberadas: coordenadas com `x` ao longo do comprimento, `y` na boca
e `z` na vertical (a tese usa `Z` no comprimento); `K` é a meia-largura do painel
plano da quilha; as espessuras de quina e de quilha são ramificadas de forma
suave entre as estações; o raio de curvatura é comparado via curvatura; o
S-TLBO usa uma "paciência" de iterações (a tese para após duas) porque as
penalidades α e β são discretas; a penalidade por restrição violada soma uma fração pequena do *grau* da violação, só para desempatar projetos inviáveis (a contagem pura é plana e deixa os alunos sem direção); e "110 ≤ β ≤ 80" do participante 3 (Tabela
4.1, impossível) foi lido como 80 ≤ β ≤ 120.

## Testes

```powershell
python -m unittest discover -v
```
