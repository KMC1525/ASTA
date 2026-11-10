// Rótulos legíveis das propriedades dos nós e das opções de listas do Game Engine (o servidor manda as chaves; a tela mostra estes textos, traduzidos em en.js).
export const PROP_LABEL = {
  x: 'X', y: 'Y', z: 'Z', rotation: 'Rotação', rx: 'Rotação X', ry: 'Rotação Y', rz: 'Rotação Z', sx: 'Escala X', sy: 'Escala Y', sz: 'Escala Z', scale: 'Escala', visible: 'Visível',
  w: 'Largura', h: 'Altura', d: 'Profundidade', color: 'Cor', color2: 'Cor 2', shape: 'Forma', image: 'Imagem', emoji: 'Emoji', opacity: 'Opacidade', solid: 'Sólido', flip: 'Espelhado', shadow: 'Sombra',
  text: 'Texto', size: 'Tamanho', align: 'Alinhamento', map: 'Mapa', objects: 'Objetos do mapa', follow: 'Seguir', zoom: 'Zoom', smooth: 'Suavização', style: 'Estilo', factor: 'Fator de paralaxe', seed: 'Semente',
  kind: 'Tipo', intensity: 'Intensidade', range: 'Alcance', mode: 'Modo', fov: 'Campo de visão', distance: 'Distância', height: 'Altura', target: 'Alvo', color_low: 'Cor baixa', color_mid: 'Cor média', color_high: 'Cor alta',
  top: 'Topo', bottom: 'Base', stars: 'Estrelas', fog: 'Névoa', level: 'Nível', skin: 'Pele', teleport: 'Teletransporte', hands: 'Mãos', anchor: 'Âncora', bind: 'Valor ligado', sound: 'Som', loop: 'Repetir', volume: 'Volume',
  rough: 'Aspereza', metal: 'Metal', emissive: 'Brilho próprio', speed: 'Velocidade', jump: 'Pulo', double_jump: 'Pulo duplo', fire_rate: 'Cadência de tiro', radius: 'Raio', axis: 'Eixo', amp: 'Amplitude', value: 'Valor',
  amount: 'Quantidade', damage: 'Dano', hp: 'Vida', score: 'Pontos', interval: 'Intervalo', next: 'Próxima cena', power: 'Força', id: 'Identificador', key: 'Chave', template: 'Modelo', max: 'Máximo', gap: 'Distância mínima',
  to_x: 'Destino X', to_z: 'Destino Z', vx: 'Velocidade X', vy: 'Velocidade Y', y_pos: 'Altura',
};
export const OPT_LABEL = {
  rect: 'Retângulo', circle: 'Círculo', tri: 'Triângulo', diamond: 'Losango', block: 'Bloco', flag: 'Bandeira', emoji: 'Emoji', none: 'Nenhum', box: 'Caixa', sphere: 'Esfera', cylinder: 'Cilindro', cone: 'Cone', capsule: 'Cápsula',
  torus: 'Anel', plane: 'Plano', octa: 'Octaedro', icosa: 'Icosaedro', directional: 'Direcional', point: 'Pontual', spot: 'Holofote', ambient: 'Ambiente', hemisphere: 'Hemisférica', hills: 'Colinas', mountains: 'Montanhas',
  clouds: 'Nuvens', stars: 'Estrelas', city: 'Cidade', trees: 'Árvores', solid: 'Cor sólida', left: 'Esquerda', center: 'Centro', right: 'Direita', 'top-left': 'Topo à esquerda', 'top-center': 'Topo ao centro', 'top-right': 'Topo à direita',
  'bottom-left': 'Base à esquerda', 'bottom-center': 'Base ao centro', 'bottom-right': 'Base à direita', first: '1ª pessoa', third: '3ª pessoa', orbit: 'Órbita', fixed: 'Fixa', hp: 'Vida', x: 'X', y: 'Y', z: 'Z',
  player: 'jogador', goal: 'objetivo', coin: 'moeda', gem: 'gema', heart: 'coração', enemy: 'inimigo', flyer: 'voador', chaser: 'perseguidor', spike: 'espinho', spring: 'mola', key: 'chave', door: 'porta', npc: 'NPC', crate: 'caixa',
  tree: 'árvore', rock: 'pedra', house: 'casa', ball: 'bola', pillar: 'pilar', portal: 'portal',
};
export const HINT_LABEL = ['camada', 'bloqueia o movimento', 'cria os objetos do mapa (moedas, inimigos…)', '{score} {coins} {total} {hp} {time} {level}', 'altura (0 topo … 1 base)', 'cena seguinte (vazio = próxima/fim)', 'id em data/dialogues.json'];
