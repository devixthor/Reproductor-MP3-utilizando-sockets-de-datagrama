import json
import os
import random
import socket

import protocolo as proto

SERVER_ADDR = ("127.0.0.1", 9999)
CARPETA_DESCARGAS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "descargas_cliente")
SIMULAR_FALLOS_RED = False
PROB_PERDIDA = 0.02
PROB_CORRUPCION = 0.02


def solicitar_catalogo(sock: socket.socket) -> list[dict]:
    paquete = proto.crear_paquete(proto.PKT_REQ_CATALOG, seq_num=0)
    sock.settimeout(3.0)

    try:
        for intento in range(3):
            try:
                sock.sendto(paquete, SERVER_ADDR)
                raw_bytes, addr = sock.recvfrom(65535)
                if addr != SERVER_ADDR:
                    continue

                es_valido, pkt_type, _, data = proto.desempaquetar_paquete(raw_bytes)
                if es_valido and pkt_type == proto.PKT_RES_CATALOG:
                    catalogo = json.loads(data.decode("utf-8"))
                    if isinstance(catalogo, list):
                        return catalogo
                    print("[!] El servidor devolvió un catálogo con formato inválido.")
                    return []
            except socket.timeout:
                print(f"[!] Tiempo de espera agotado al pedir catálogo (intento {intento + 1}/3).")
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                print(f"[!] No se pudo interpretar el catálogo recibido: {exc}")
                return []
    finally:
        sock.settimeout(None)

    return []


def descargar_cancion_gbn(sock: socket.socket, nombre_archivo: str) -> str | None:
    if (
        not nombre_archivo
        or os.path.basename(nombre_archivo) != nombre_archivo
        or not nombre_archivo.lower().endswith(".mp3")
    ):
        print("[!] El nombre de archivo recibido no es válido.")
        return None

    os.makedirs(CARPETA_DESCARGAS, exist_ok=True)
    ruta_destino = os.path.join(CARPETA_DESCARGAS, nombre_archivo)
    ruta_temporal = ruta_destino + ".part"
    req_pkt = proto.crear_paquete(
        proto.PKT_REQ_SONG,
        seq_num=0,
        data=nombre_archivo.encode("utf-8"),
    )
    sock.settimeout(5.0)
    expected_seq_num = 0
    bytes_recibidos = 0
    paquetes_descartados = 0
    descarga_completa = False

    print(f"\n[GBN RECEPTOR] Iniciando descarga confiable de '{nombre_archivo}'...")

    try:
        sock.sendto(req_pkt, SERVER_ADDR)
        with open(ruta_temporal, "wb") as archivo_mp3:
            while True:
                try:
                    raw_bytes, addr = sock.recvfrom(proto.BUFFER_SIZE)
                except socket.timeout:
                    print("\n[!] Error: el servidor dejó de responder durante la transferencia.")
                    return None

                if addr != SERVER_ADDR:
                    continue

                if SIMULAR_FALLOS_RED and len(raw_bytes) >= proto.HEADER_SIZE:
                    tipo_espia = raw_bytes[0]
                    if tipo_espia == proto.PKT_DATA:
                        if random.random() < PROB_PERDIDA:
                            _, _, seq_perdido, _ = proto.desempaquetar_paquete(raw_bytes)
                            print(f"  [SIMULADOR RED] Se perdió el paquete Seq={seq_perdido}.")
                            paquetes_descartados += 1
                            continue

                        if random.random() < PROB_CORRUPCION:
                            paquete_corrupto = bytearray(raw_bytes)
                            paquete_corrupto[-1] ^= 0xFF
                            raw_bytes = bytes(paquete_corrupto)

                es_valido, pkt_type, seq_num, data = proto.desempaquetar_paquete(raw_bytes)
                if not es_valido:
                    paquetes_descartados += 1
                    print("  [CHECKSUM ERROR] Trama corrupta detectada y descartada.")
                    if expected_seq_num > 0:
                        ack_pkt = proto.crear_paquete(
                            proto.PKT_ACK,
                            seq_num=expected_seq_num - 1,
                        )
                        sock.sendto(ack_pkt, SERVER_ADDR)
                    continue

                if pkt_type == proto.PKT_ERROR:
                    print(f"\n[!] Error del servidor: {data.decode('utf-8', errors='replace')}")
                    return None

                if pkt_type == proto.PKT_DATA:
                    if seq_num == expected_seq_num:
                        archivo_mp3.write(data)
                        bytes_recibidos += len(data)
                        ack_pkt = proto.crear_paquete(
                            proto.PKT_ACK,
                            seq_num=expected_seq_num,
                        )
                        sock.sendto(ack_pkt, SERVER_ADDR)

                        if expected_seq_num % 25 == 0:
                            print(
                                f"  [OK] Seq={expected_seq_num} escrito "
                                f"({bytes_recibidos / 1024:.1f} KB)."
                            )
                        expected_seq_num += 1
                    else:
                        paquetes_descartados += 1
                        print(
                            f"  [FUERA DE ORDEN] Llegó Seq={seq_num}, "
                            f"se esperaba Seq={expected_seq_num}."
                        )
                        if expected_seq_num > 0:
                            ack_dup = proto.crear_paquete(
                                proto.PKT_ACK,
                                seq_num=expected_seq_num - 1,
                            )
                            sock.sendto(ack_dup, SERVER_ADDR)

                elif pkt_type == proto.PKT_FIN and seq_num == expected_seq_num:
                    ack_fin = proto.crear_paquete(
                        proto.PKT_ACK,
                        seq_num=expected_seq_num,
                    )
                    sock.sendto(ack_fin, SERVER_ADDR)

                elif pkt_type == proto.PKT_FIN_CONFIRM and seq_num == expected_seq_num:
                    descarga_completa = True
                    break

        if not descarga_completa:
            return None

        os.replace(ruta_temporal, ruta_destino)
        print("\n[+] Descarga completada.")
        print(f"[*] Paquetes descartados: {paquetes_descartados}.")
        return ruta_destino
    finally:
        sock.settimeout(None)
        if os.path.exists(ruta_temporal):
            os.remove(ruta_temporal)


def reproducir_cancion(ruta: str) -> None:
    try:
        os.startfile(ruta)
        print("\n[*] Abriendo la canción con el reproductor predeterminado de Windows.")
    except OSError as exc:
        print(f"[!] No se pudo reproducir el archivo: {exc}")


def iniciar_cliente() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        catalogo = solicitar_catalogo(sock)
        if not catalogo:
            print("[!] El catálogo está vacío o no se pudo obtener.")
            print("[*] Agrega archivos MP3 a la carpeta catalogo_servidor del servidor.")
            return

        print("\n=== CATÁLOGO DE CANCIONES ===")
        for cancion in catalogo:
            print(
                f"{cancion.get('id', '?')}. "
                f"{cancion.get('titulo', 'Sin título')} — "
                f"{cancion.get('artista', 'Artista desconocido')} "
                f"({cancion.get('archivo', 'archivo desconocido')})"
            )

        while True:
            seleccion = input("\nNúmero para descargar/reproducir, o 'q' para salir: ").strip()
            if seleccion.lower() == "q":
                return

            try:
                cancion_id = int(seleccion)
            except ValueError:
                print("[!] Escribe un número de la lista o 'q'.")
                continue

            cancion = next(
                (elemento for elemento in catalogo if elemento.get("id") == cancion_id),
                None,
            )
            if cancion is None or not isinstance(cancion.get("archivo"), str):
                print("[!] La selección no corresponde a una canción del catálogo.")
                continue

            ruta = descargar_cancion_gbn(sock, cancion["archivo"])
            if ruta is not None:
                reproducir_cancion(ruta)


if __name__ == "__main__":
    try:
        from interfaz import iniciar_interfaz

        iniciar_interfaz()
    except KeyboardInterrupt:
        print("\n[*] Cliente detenido.")
