import struct
import zlib
import os

HEADER_FORMAT = '!BIIH'
HEADER_SIZE = struct.calcsize(HEADER_FORMAT)  
PAYLOAD_SIZE = 1024                          
BUFFER_SIZE = HEADER_SIZE + PAYLOAD_SIZE + 64 
WINDOW_SIZE = 5   
TIMEOUT = 0.25 

PKT_REQ_CATALOG = 0  
PKT_RES_CATALOG = 1  
PKT_REQ_SONG    = 2  
PKT_DATA        = 3  
PKT_ACK         = 4 
PKT_FIN         = 5  
PKT_ERROR       = 6  
PKT_FIN_CONFIRM = 7


def crear_paquete(pkt_type: int, seq_num: int, data: bytes = b'') -> bytes:
    length = len(data)
    temp_header = struct.pack(HEADER_FORMAT, pkt_type, seq_num, length, 0)
    checksum = zlib.crc32(temp_header + data) & 0xFFFF
    header = struct.pack(HEADER_FORMAT, pkt_type, seq_num, length, checksum)
    return header + data


def desempaquetar_paquete(raw_bytes: bytes) -> tuple[bool, int, int, bytes]:
    if len(raw_bytes) < HEADER_SIZE:
        return False, -1, -1, b''
        
    header = raw_bytes[:HEADER_SIZE]
    data = raw_bytes[HEADER_SIZE:]
    
    pkt_type, seq_num, length, recv_checksum = struct.unpack(HEADER_FORMAT, header)
    
    temp_header = struct.pack(HEADER_FORMAT, pkt_type, seq_num, length, 0)
    calc_checksum = zlib.crc32(temp_header + data) & 0xFFFF
    
    es_valido = (recv_checksum == calc_checksum) and (len(data) == length)
    return es_valido, pkt_type, seq_num, data

def _decodificar_synchsafe(cuatro_bytes: bytes) -> int:
    b0, b1, b2, b3 = cuatro_bytes
    return (b0 << 21) | (b1 << 14) | (b2 << 7) | b3


def _decodificar_texto_frame(contenido_frame: bytes) -> str:
    if not contenido_frame:
        return ""
    encoding_byte = contenido_frame[0]
    raw_text = contenido_frame[1:]

    if encoding_byte == 0:
        texto = raw_text.decode('latin-1', errors='ignore')
    elif encoding_byte == 1:
        texto = raw_text.decode('utf-16', errors='ignore')
    elif encoding_byte == 2:
        texto = raw_text.decode('utf-16-be', errors='ignore')
    else:
        texto = raw_text.decode('utf-8', errors='ignore')

    return texto.replace('\x00', '').strip()


GENEROS_ID3 = {
    0: "Blues",
    1: "Rock clásico",
    2: "Country",
    3: "Dance",
    4: "Disco",
    5: "Funk",
    6: "Grunge",
    7: "Hip-hop",
    8: "Jazz",
    9: "Metal",
    10: "New age",
    11: "Oldies",
    12: "Otros",
    13: "Pop",
    14: "R&B",
    15: "Rap",
    16: "Reggae",
    17: "Rock",
    18: "Techno",
    19: "Industrial",
    20: "Alternative",
    21: "Ska",
    22: "Death metal",
    24: "Soundtrack",
    26: "Ambient",
    27: "Trip-hop",
    28: "Vocal",
    29: "Jazz + funk",
    30: "Fusion",
    31: "Trance",
    32: "Classical",
    33: "Instrumental",
    34: "Acid",
    35: "House",
    36: "Game",
    37: "Sound clip",
    38: "Gospel",
    39: "Noise",
    40: "Alternative rock",
    41: "Bass",
    42: "Soul",
    43: "Punk",
    44: "Space",
    45: "Meditative",
    46: "Instrumental pop",
    47: "Instrumental rock",
    48: "Ethnic",
    49: "Gothic",
    50: "Darkwave",
    51: "Techno-industrial",
    52: "Electronic",
    53: "Pop-folk",
    54: "Eurodance",
    55: "Dream",
    56: "Southern rock",
    57: "Comedy",
    58: "Cult",
    59: "Gangsta",
    60: "Top 40",
    61: "Christian rap",
    62: "Pop/funk",
    63: "Jungle",
    64: "Native American",
    65: "Cabaret",
    66: "New wave",
    67: "Psychedelic",
    68: "Rave",
    69: "Showtunes",
    70: "Trailer",
    71: "Lo-fi",
    72: "Tribal",
    73: "Acid punk",
    74: "Acid jazz",
    75: "Polka",
    76: "Retro",
    77: "Musical",
    78: "Rock & roll",
    79: "Hard rock",
}


def _normalizar_genero(texto: str) -> str:
    texto = texto.strip()
    if texto.startswith("(") and ")" in texto:
        codigo, resto = texto[1:].split(")", 1)
        if codigo.isdigit():
            return GENEROS_ID3.get(int(codigo), resto.strip() or "Sin género")
    return texto or "Sin género"


def leer_metadatos_id3(ruta_mp3: str) -> dict:
    info = {
        "archivo": os.path.basename(ruta_mp3),
        "tamano_kb": round(os.path.getsize(ruta_mp3) / 1024, 2),
        "formato_id3": "Sin etiqueta ID3",
        "titulo": os.path.basename(ruta_mp3),
        "artista": "Desconocido",
        "album": "Desconocido",
        "genero": "Sin género",
        "duracion_seg": 0,
        "anio": "----"
    }

    with open(ruta_mp3, 'rb') as f:
        cabecera_v2 = f.read(10)
        if len(cabecera_v2) == 10 and cabecera_v2[:3] == b'ID3':
            version_mayor = cabecera_v2[3]  
            tam_tag = _decodificar_synchsafe(cabecera_v2[6:10])
            
            datos_v2 = f.read(tam_tag)
            pos = 0
            encontro_frames = False
            
            while pos + 10 <= len(datos_v2):
                frame_id = datos_v2[pos:pos+4].decode('ascii', errors='ignore')
                if not frame_id.isalnum():
                    break
                
                bytes_tam = datos_v2[pos+4 : pos+8]
                if version_mayor == 4:
                    frame_size = _decodificar_synchsafe(bytes_tam)
                else:
                    frame_size = struct.unpack('!I', bytes_tam)[0]

                if frame_size <= 0 or pos + 10 + frame_size > len(datos_v2):
                    break
                    
                contenido = datos_v2[pos+10 : pos+10+frame_size]
                texto = _decodificar_texto_frame(contenido)

                if frame_id == 'TIT2' and texto:
                    info['titulo'] = texto
                    encontro_frames = True
                elif frame_id == 'TPE1' and texto:
                    info['artista'] = texto
                    encontro_frames = True
                elif frame_id == 'TALB' and texto:
                    info['album'] = texto
                elif frame_id == 'TCON' and texto:
                    info['genero'] = _normalizar_genero(texto.split('\x00', 1)[0])
                elif frame_id == 'TLEN' and texto.isdigit():
                    info['duracion_seg'] = int(texto) // 1000
                elif frame_id in ('TYER', 'TDRC') and texto:
                    info['anio'] = texto[:4]

                pos += 10 + frame_size

            if encontro_frames:
                info["formato_id3"] = f"ID3v2.{version_mayor}"
                return info
            
        if os.path.getsize(ruta_mp3) >= 128:
            f.seek(-128, os.SEEK_END)
            tag_v1 = f.read(128)
            if tag_v1[:3] == b'TAG':
                info["formato_id3"] = "ID3v1"
                info["titulo"]  = tag_v1[3:33].decode('latin-1', errors='ignore').rstrip('\x00').strip()
                info["artista"] = tag_v1[33:63].decode('latin-1', errors='ignore').rstrip('\x00').strip()
                info["album"]   = tag_v1[63:93].decode('latin-1', errors='ignore').rstrip('\x00').strip()
                info["anio"]    = tag_v1[93:97].decode('latin-1', errors='ignore').rstrip('\x00').strip()
                codigo_genero = tag_v1[127]
                info["genero"] = GENEROS_ID3.get(codigo_genero, "Sin género")

    return info