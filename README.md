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
  raio mínimo no painel lateral. Cada campo traz sua unidade e seu intervalo.
- Escolha um dos 10 perfis navais na barra superior; ao editar qualquer campo o
  seletor passa a indicar **Personalizado**, para não rotular o casco com o nome
  de um preset que ele já não segue.
- Use **Atualizar modelo 3D**, `Enter` em qualquer campo ou `Ctrl+Enter` para
  recalcular o casco. O painel avisa quando o formulário está à frente da malha.
- O **raio mínimo** é o raio real da curvatura da quilha na seção mestra:
  valores maiores achatam o fundo, valores menores deixam a quilha mais viva.
  O limite exibido é geométrico, dado por `(meia-boca² + calado²) / (2 · calado)`.
- O **ângulo de proa** afina apenas a entrada de proa e não altera a popa.
- Importe malhas STL, OBJ, PLY, VTK ou VTP pelo menu **Arquivo > Abrir casco**
  ou arrastando o arquivo para a janela.
- Desloque, rotacione ou redimensione o modelo inteiro no grupo
  **Transformar objeto**. A câmera é preservada a cada operação.
- Use `Ctrl+Z` e `Ctrl+Y` para desfazer e refazer transformações. O histórico
  guarda as 20 operações mais recentes.
- Exporte o modelo visível em STL, PLY, VTK ou VTP.
- Use o mouse para orbitar, deslocar e aproximar a câmera.
- Pressione `F` para **enquadrar o modelo** mantendo a orientação atual, e
  `Home` para voltar à **vista isométrica**.

Malhas importadas já podem ser transformadas e convertidas. A seleção e edição
direta de seus pontos e faces fará parte da próxima etapa do MVP.

## Testes

```powershell
python -m unittest discover -v
```
