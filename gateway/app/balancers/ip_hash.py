"""IP hash: o mesmo IP de cliente cai sempre no mesmo upstream.

    índice = hash(ip) % quantidade_de_upstreams_no_pool

Dá afinidade de sessão sem cookie (funciona para qualquer cliente HTTP), mas a
distribuição depende de como os IPs se espalham: muitos usuários atrás do
mesmo NAT/proxy caem todos no mesmo servidor.

Dois detalhes importantes:
- Não usamos o hash() do Python: o hash() de strings muda a cada processo
  (PYTHONHASHSEED), então depois de um restart o mapeamento mudaria.
- Também não serve qualquer hash estável: com crc32, 10.0.0.1, 10.0.0.2 e
  10.0.0.3 caem TODOS no mesmo upstream (crc32 é linear e IPs vizinhos geram
  restos parecidos). O md5 espalha bem; aqui não é questão de segurança.
- O índice é calculado sobre o pool INTEIRO, não só os disponíveis. Se o
  escolhido estiver fora, andamos para o próximo. Assim, quando um servidor
  cai, só os clientes dele mudam de lugar; se calculássemos sobre a lista de
  disponíveis, quase todos os clientes seriam remapeados. (Consistent hashing
  leva essa ideia mais longe.)

Teste: curl -H 'X-Forwarded-For: 10.0.0.1' -i localhost:8080/users  (troque o IP)
"""

import hashlib

from .base import Balancer


class IpHash(Balancer):
    name = "ip_hash"

    def pick(self, candidates, ctx):
        pool = ctx.pool or candidates
        digest = hashlib.md5(ctx.client_ip.encode()).digest()
        start = int.from_bytes(digest[:8], "big") % len(pool)
        for offset in range(len(pool)):
            upstream = pool[(start + offset) % len(pool)]
            if upstream in candidates:
                return upstream
        return candidates[0]
