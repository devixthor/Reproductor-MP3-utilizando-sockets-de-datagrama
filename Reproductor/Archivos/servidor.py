import socket
import json
import os
import requests
import protocolo as proto

SERVER_IP = '127.0.0.1'
SERVER_PORT = 9999
CARPETA_MP3 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "catalogo_servidor")
JAMENDO_CLIENT_ID = os.environ.get("JAMENDO_CLIENT_ID")


def sincronizar_catalogo_jamendo(busqueda: str = "rap", limite: int = 5):
    os.makedirs(CARPETA_MP3, exist_ok=True)
    
    if not JAMENDO_CLIENT_ID:
        print("[*] JAMENDO_CLIENT_ID no está configurado; se usarán los MP3 locales.")
        return

    print(f"[*] Consultando Jamendo API (búsqueda='{busqueda}', límite={limite})...")
    url = "https://api.jamendo.com/v3.0/tracks/"
    params = {
        "client_id": JAMENDO_CLIENT_ID,
        "format": "json",
        "limit": limite,
        "search": busqueda,
        "audioformat": "mp32",
        "include": "musicinfo",
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        datos = resp.json()
        resultados = datos.get("results", [])

        if not resultados:
            encabezados = datos.get("headers", {})
            estado = encabezados.get("status", "desconocido")
            codigo = encabezados.get("code", "desconocido")
            detalle = encabezados.get("error_message") or encabezados.get("warnings") or "sin detalle"
            print(
                f"[!] Jamendo no devolvió pistas para '{busqueda}' "
                f"(estado={estado}, código={codigo}, detalle={detalle})."
            )
            return

        ruta_metadata = os.path.join(CARPETA_MP3, ".jamendo_metadata.json")
        try:
            with open(ruta_metadata, "r", encoding="utf-8") as archivo:
                metadata_catalogo = json.load(archivo)
            if not isinstance(metadata_catalogo, dict):
                raise ValueError("El archivo de metadatos de Jamendo no contiene un objeto JSON.")
        except FileNotFoundError:
            metadata_catalogo = {}
        except (OSError, ValueError) as e:
            print(f"[!] No se pudo leer la metadata previa de Jamendo: {e}")
            metadata_catalogo = {}

        for track in resultados:
            track_id = track.get("id")
            titulo = track.get("name", "Sin titulo")
            artista = track.get("artist_name", "Artista Jamendo")
            musicinfo = track.get("musicinfo") or {}
            tags = musicinfo.get("tags", {}) if isinstance(musicinfo, dict) else {}
            generos = tags.get("genres", []) if isinstance(tags, dict) else []
            duracion = track.get("duration", 0)
            if isinstance(generos, str):
                genero = generos.split(",", 1)[0].strip() or "Sin género"
            elif isinstance(generos, list) and generos:
                genero = str(generos[0]).strip() or "Sin género"
            else:
                genero = "Sin género"
            try:
                duracion_seg = int(float(duracion))
            except (TypeError, ValueError):
                duracion_seg = 0
            metadata_catalogo[f"jamendo_{track_id}.mp3"] = {
                "genero": genero,
                "duracion_seg": duracion_seg,
            }
            mp3_url = track.get("audiodownload") or track.get("audio")
            if not mp3_url:
                continue

            nombre_archivo = f"jamendo_{track_id}.mp3"
            ruta_destino = os.path.join(CARPETA_MP3, nombre_archivo)

            if not os.path.exists(ruta_destino):
                print(f"    -> Descargando de Jamendo: '{titulo}' - {artista}...")
                audio_resp = requests.get(mp3_url, timeout=20)
                audio_resp.raise_for_status()
                with open(ruta_destino, 'wb') as f:
                    f.write(audio_resp.content)

        ruta_temporal = ruta_metadata + ".tmp"
        with open(ruta_temporal, "w", encoding="utf-8") as archivo:
            json.dump(metadata_catalogo, archivo, ensure_ascii=False, indent=2)
        os.replace(ruta_temporal, ruta_metadata)
        print("[+] Catálogo de Jamendo sincronizado correctamente en el servidor.\n")

    except (requests.RequestException, ValueError) as e:
        print(f"[!] Error al conectar con Jamendo API: {e}")


def obtener_menu_id3() -> list[dict]:
    catalogo = []
    os.makedirs(CARPETA_MP3, exist_ok=True)
    archivos = sorted([f for f in os.listdir(CARPETA_MP3) if f.lower().endswith('.mp3')])
    ruta_metadata = os.path.join(CARPETA_MP3, ".jamendo_metadata.json")
    try:
        with open(ruta_metadata, "r", encoding="utf-8") as archivo:
            metadata_catalogo = json.load(archivo)
        if not isinstance(metadata_catalogo, dict):
            raise ValueError("El archivo de metadatos de Jamendo no contiene un objeto JSON.")
    except FileNotFoundError:
        metadata_catalogo = {}
    except (OSError, ValueError) as e:
        print(f"[!] No se pudo leer la metadata de Jamendo: {e}")
        metadata_catalogo = {}

    for idx, nombre in enumerate(archivos, start=1):
        ruta = os.path.join(CARPETA_MP3, nombre)
        metadatos = proto.leer_metadatos_id3(ruta)
        metadata_jamendo = metadata_catalogo.get(nombre, {})
        if isinstance(metadata_jamendo, dict):
            if metadatos["genero"] == "Sin género":
                metadatos["genero"] = metadata_jamendo.get("genero", "Sin género")
            if not metadatos["duracion_seg"]:
                metadatos["duracion_seg"] = metadata_jamendo.get("duracion_seg", 0)
        metadatos["id"] = idx
        catalogo.append(metadatos)

    return catalogo

def enviar_archivo_gbn(sock: socket.socket, client_addr: tuple, ruta_mp3: str):
    chunks = []
    with open(ruta_mp3, 'rb') as f:
        while True:
            bloque = f.read(proto.PAYLOAD_SIZE)
            if not bloque:
                break
            chunks.append(bloque)

    total_paquetes = len(chunks)
    print(f"\n[GBN INICIO] Archivo: '{os.path.basename(ruta_mp3)}' ({total_paquetes} paquetes de {proto.PAYLOAD_SIZE}B)")
    print(f"[GBN CONFIG] Tamaño de Ventana (N) = {proto.WINDOW_SIZE} | Timeout = {proto.TIMEOUT}s\n")

    base = 0          
    next_seq_num = 0  
    retransmisiones = 0
    sock.settimeout(proto.TIMEOUT)

    while base < total_paquetes:
        while next_seq_num < base + proto.WINDOW_SIZE and next_seq_num < total_paquetes:
            paquete = proto.crear_paquete(
                pkt_type=proto.PKT_DATA,
                seq_num=next_seq_num,
                data=chunks[next_seq_num]
            )
            sock.sendto(paquete, client_addr)
            print(f"  [ENVÍO] Seq={next_seq_num} enviado | Ventana activa: [{base} .. {min(base + proto.WINDOW_SIZE - 1, total_paquetes - 1)}]")
            next_seq_num += 1

        try:
            raw_bytes, addr = sock.recvfrom(proto.BUFFER_SIZE)
            if addr != client_addr:
                continue  

            es_valido, pkt_type, ack_num, _ = proto.desempaquetar_paquete(raw_bytes)

            if not es_valido:
                print("  [!] ACK corrupto recibido (Checksum inválido). Ignorando...")
                continue

            if pkt_type == proto.PKT_ACK:
                if base <= ack_num < next_seq_num:
                    print(f"  [ACK RECIBIDO] Confirmado hasta Seq={ack_num}. Deslizando ventana -> nueva base={ack_num + 1}")
                    base = ack_num + 1
                else:
                    print(f"  [ACK DUPLICADO] Recibido ACK={ack_num} (base actual={base})")

        except socket.timeout:
            retransmisiones += 1
            print(f"  [TIMEOUT #{retransmisiones}] Retrocediendo-N -> Retransmitiendo desde Seq={base} hasta {next_seq_num - 1}")
            next_seq_num = base

    print(f"\n[GBN FIN] Todos los {total_paquetes} paquetes fueron confirmados. Enviando trama FIN...")
    paquete_fin = proto.crear_paquete(proto.PKT_FIN, seq_num=total_paquetes)
    
    confirmado = False
    for _ in range(5):
        sock.sendto(paquete_fin, client_addr)
        try:
            raw_bytes, addr = sock.recvfrom(proto.BUFFER_SIZE)
            es_valido, pkt_type, ack_num, _ = proto.desempaquetar_paquete(raw_bytes)
            if (
                addr == client_addr
                and es_valido
                and pkt_type == proto.PKT_ACK
                and ack_num == total_paquetes
            ):
                confirmacion = proto.crear_paquete(
                    proto.PKT_FIN_CONFIRM,
                    seq_num=total_paquetes,
                )
                sock.sendto(confirmacion, client_addr)
                confirmado = True
                print(f"[GBN COMPLETO] Transferencia exitosa. Total de eventos Timeout/Retroceder-N: {retransmisiones}\n")
                break
        except socket.timeout:
            print("  [!] Reenviando paquete FIN...")
    if not confirmado:
        print("[!] No se confirmó el cierre de la transferencia.")
    sock.settimeout(None)

def iniciar_servidor():
    sincronizar_catalogo_jamendo(busqueda="classical", limite=10)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((SERVER_IP, SERVER_PORT))
    print(f"=== SERVIDOR MP3 UDP ACTIVO EN {SERVER_IP}:{SERVER_PORT} ===")

    while True:
        print("\nEsperando peticiones de clientes...")
        raw_bytes, client_addr = sock.recvfrom(proto.BUFFER_SIZE)
        es_valido, pkt_type, _, data = proto.desempaquetar_paquete(raw_bytes)

        if not es_valido:
            print(f"[!] Trama corrupta desde {client_addr}. Ignorando.")
            continue
        if pkt_type == proto.PKT_REQ_CATALOG:
            print(f"[*] Cliente {client_addr} solicitó el catálogo ID3.")
            catalogo = obtener_menu_id3()
            json_bytes = json.dumps(catalogo, ensure_ascii=False).encode('utf-8')
            
            respuesta = proto.crear_paquete(proto.PKT_RES_CATALOG, seq_num=0, data=json_bytes)
            sock.sendto(respuesta, client_addr)
            print(f"[+] Catálogo enviado ({len(catalogo)} canciones encontradas).")

        elif pkt_type == proto.PKT_REQ_SONG:
            nombre_archivo = data.decode('utf-8', errors='ignore').strip()
            if (
                not nombre_archivo
                or os.path.basename(nombre_archivo) != nombre_archivo
                or not nombre_archivo.lower().endswith('.mp3')
            ):
                msg_err = "Nombre de archivo no válido.".encode('utf-8')
                pkt_err = proto.crear_paquete(proto.PKT_ERROR, seq_num=0, data=msg_err)
                sock.sendto(pkt_err, client_addr)
                continue

            ruta_mp3 = os.path.join(CARPETA_MP3, nombre_archivo)
            print(f"[*] Cliente {client_addr} solicitó descargar: '{nombre_archivo}'")

            if os.path.exists(ruta_mp3):
                enviar_archivo_gbn(sock, client_addr, ruta_mp3)
            else:
                msg_err = f"El archivo '{nombre_archivo}' no existe en el servidor.".encode('utf-8')
                pkt_err = proto.crear_paquete(proto.PKT_ERROR, seq_num=0, data=msg_err)
                sock.sendto(pkt_err, client_addr)


if __name__ == '__main__':
    iniciar_servidor()
