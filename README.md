# Odisseu

Odisseu é um protótipo desktop para modelagem paramétrica e visualização 3D de
cascos de embarcações.

## Como executar

```powershell
pip install -r requirements.txt
python main.py
```

## Fluxo atual do MVP

- Ajuste comprimento, seção média, boca, calado, ângulo de proa, concavidade e
  quantidade de linhas longitudinais no painel lateral. A resolução padrão é de
  64 seções, mas pode ser alterada entre 4 e 512.
- **Pontos por seção** define a resolução transversal (padrão 33, ímpar, entre 5
  e 257). As seções são distribuídas de forma adaptativa: há mais seções onde a
  forma do casco muda (transição para proa e popa) e menos na seção média.
- Escolha um dos 10 perfis navais na barra superior; depois edite seus parâmetros
  livremente no painel antes de atualizar o modelo.
- A quantidade de linhas longitudinais é mantida separadamente para cada perfil:
  alterar a resolução de um casco não altera os demais.
- Use **Atualizar modelo 3D** para recalcular o casco.
- Importe malhas STL, OBJ, PLY, VTK ou VTP pelo menu **Arquivo > Abrir casco**
  ou arrastando o arquivo para a janela.
- Desloque, rotacione ou redimensione o modelo inteiro no grupo
  **Transformar objeto**.
- Use `Ctrl+Z` e `Ctrl+Y` para desfazer e refazer transformações.
- Exporte o modelo visível em STL, PLY, VTK ou VTP.
- Use o mouse para orbitar, deslocar e aproximar a câmera.
- Pressione `F` para enquadrar o modelo e `Home` para redefinir a vista.

## Modelagem por atributos

A aba **Atributos** segue a seção 5.2 e a Figura 5.6 da tese *Parametric Yacht
Models* (ModiYacht):

- Cada um dos 10 atributos (Strong, Speedy, Comfortable, Aesthetic, Usual,
  Aggressive, Compact, Modern, Charismatic, Cute) é avaliado por um polinômio no
  formato GMDH (termos lineares, `cubert`, quadráticos e produtos) sobre os
  parâmetros **padronizados** do casco. O casco expressa o atributo quando o
  valor é maior que 0,5. A avaliação é atualizada enquanto os campos são editados.
- Em **Gerar cascos por atributo**, escolha um ou mais atributos e o número de
  projetos (N). O S-TLBO amostra N cascos distintos que satisfazem todos os
  atributos; o controle deslizante percorre os projetos amostrados.

Os coeficientes de Dogan dependem das curvas de forma do ModiYacht e aparecem
truncados na figura. Por isso `app/models/attributes.py` usa um **modelo
substituto** com a mesma estrutura, calibrado para os parâmetros deste gerador;
ele pode ser trocado por coeficientes ajustados a dados de pesquisa.

Malhas importadas já podem ser transformadas e convertidas. A seleção e edição
direta de seus pontos e faces fará parte da próxima etapa do MVP.

## Testes

```powershell
python -m unittest discover -v
```
