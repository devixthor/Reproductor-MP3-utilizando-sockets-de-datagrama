import os
import queue
import socket
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import pygame
from cliente import CARPETA_DESCARGAS, descargar_cancion_gbn, solicitar_catalogo

FONDO = "#0b100f"
PANEL = "#131b18"
PANEL_CLARO = "#1a2420"
LINEA = "#28352f"
TEXTO = "#f1f5f0"
SUAVE = "#8d9b91"
VERDE = "#b8f36b"
VERDE_OSCURO = "#1e3022"


class ReproductorMp3:
    def __init__(self) -> None:
        self.inicializado = False
        self.abierto = False
        self.pausado = False
        self._volumen = 0.72

    def reproducir(self, ruta: str) -> None:
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
            pygame.mixer.music.set_volume(self._volumen)
            pygame.mixer.music.stop()
            pygame.mixer.music.load(ruta)
            pygame.mixer.music.play()
            self.abierto = True
            self.inicializado = True
            self.pausado = False
        except pygame.error as exc:
            self.abierto = False
            raise RuntimeError(f"pygame no pudo reproducir el archivo: {exc}") from exc

    def alternar_pausa(self) -> bool:
        if not self.abierto:
            return False
        try:
            if self.pausado:
                pygame.mixer.music.unpause()
            else:
                pygame.mixer.music.pause()
        except pygame.error as exc:
            raise RuntimeError(f"pygame no pudo cambiar la reproducción: {exc}") from exc
        self.pausado = not self.pausado
        return self.pausado

    def detener(self) -> None:
        if self.abierto:
            try:
                pygame.mixer.music.stop()
            except pygame.error as exc:
                raise RuntimeError(f"pygame no pudo detener la reproducción: {exc}") from exc
            finally:
                self.abierto = False
                self.pausado = False

    def reproduciendo(self) -> bool:
        return self.abierto and not self.pausado and pygame.mixer.music.get_busy()

    def posicion(self) -> int:
        if not self.abierto:
            return 0
        return max(0, pygame.mixer.music.get_pos() // 1000)

    def buscar(self, segundos: float) -> None:
        try:
            pygame.mixer.music.set_pos(max(0, segundos))
        except pygame.error as exc:
            raise RuntimeError(f"No se pudo cambiar la posición de la canción: {exc}") from exc

    def volumen(self, valor: float) -> None:
        self._volumen = min(1.0, max(0.0, valor))
        if not pygame.mixer.get_init():
            return
        try:
            pygame.mixer.music.set_volume(self._volumen)
        except pygame.error as exc:
            raise RuntimeError(f"No se pudo cambiar el volumen: {exc}") from exc

    def cerrar(self) -> None:
        self.detener()
        if self.inicializado and pygame.mixer.get_init():
            pygame.mixer.quit()
            self.inicializado = False


class InterfazReproductor:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("SONORA  /  MP3 PLAYER")
        self.root.geometry("1180x760")
        self.root.minsize(900, 610)
        self.root.configure(bg=FONDO)
        self.root.protocol("WM_DELETE_WINDOW", self.cerrar)

        self.reproductor = ReproductorMp3()
        self.cola: queue.Queue[tuple[str, object]] = queue.Queue()
        self.catalogo: list[dict] = []
        self.generos: list[str] = []
        self.genero_actual = "Toda la música"
        self.cancion_actual: dict | None = None
        self.duracion_actual = 0
        self.seleccionando_posicion = False
        self.filtro = tk.StringVar()
        self.genero_texto = tk.StringVar(value="Toda la música")
        self.titulo_actual = tk.StringVar(value="Elige una canción")
        self.artista_actual = tk.StringVar(value="Tu música, a tu manera")
        self.estado = tk.StringVar(value="Conectando con tu biblioteca...")
        self.tiempo_actual = tk.StringVar(value="0:00")
        self.tiempo_total = tk.StringVar(value="0:00")
        self.volumen = tk.DoubleVar(value=72)

        self._configurar_estilos()
        self._crear_interfaz()
        self.filtro.trace_add("write", self._dibujar_canciones)
        self.root.bind("<space>", self._atajo_pausa)
        self.root.bind("<Double-1>", self._doble_click)
        self.root.after(100, self._procesar_cola)
        self.root.after(250, self._actualizar_reproduccion)
        self.actualizar_catalogo()

    def _configurar_estilos(self) -> None:
        estilo = ttk.Style(self.root)
        estilo.theme_use("clam")
        estilo.configure(
            "Library.Treeview",
            background=PANEL,
            fieldbackground=PANEL,
            foreground=TEXTO,
            borderwidth=0,
            rowheight=42,
            font=("Segoe UI", 10),
        )
        estilo.configure(
            "Library.Treeview.Heading",
            background=PANEL,
            foreground=SUAVE,
            relief="flat",
            borderwidth=0,
            font=("Segoe UI Semibold", 9),
        )
        estilo.map(
            "Library.Treeview",
            background=[("selected", VERDE_OSCURO)],
            foreground=[("selected", VERDE)],
        )
        estilo.configure(
            "Library.Vertical.TScrollbar",
            background=PANEL,
            troughcolor=PANEL,
            bordercolor=PANEL,
            arrowcolor=SUAVE,
        )
        estilo.configure(
            "Library.Horizontal.TScale",
            background=PANEL,
            troughcolor=LINEA,
            sliderthickness=12,
        )

    def _crear_interfaz(self) -> None:
        shell = tk.Frame(self.root, bg=FONDO)
        shell.pack(fill=tk.BOTH, expand=True)
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(1, weight=1)

        self.sidebar = tk.Frame(shell, bg=PANEL, width=235)
        self.sidebar.grid(row=0, column=0, sticky="ns")
        self.sidebar.grid_propagate(False)
        self._crear_sidebar()

        contenido = tk.Frame(shell, bg=FONDO)
        contenido.grid(row=0, column=1, sticky="nsew")
        contenido.rowconfigure(3, weight=1)
        contenido.columnconfigure(0, weight=1)
        self._crear_contenido(contenido)
        self._crear_reproductor(shell)

    def _crear_sidebar(self) -> None:
        tk.Label(
            self.sidebar,
            text="POLIMUSIC",
            bg=PANEL,
            fg=VERDE,
            font=("Segoe UI", 18, "bold"),
            anchor="w",
        ).pack(fill="x", padx=24, pady=(26, 4))
        tk.Label(
            self.sidebar,
            text="TU ESPACIO MUSICAL",
            bg=PANEL,
            fg=SUAVE,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=27, pady=(0, 30))

        self._etiqueta_sidebar("BIBLIOTECA")
        contenedor_generos = tk.Frame(self.sidebar, bg=PANEL)
        contenedor_generos.pack(fill="x", padx=14)
        self.lista_generos = tk.Listbox(
            self.sidebar,
            bg=PANEL,
            fg="#b9c4bc",
            selectbackground=VERDE_OSCURO,
            selectforeground=VERDE,
            activestyle="none",
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=("Segoe UI", 10),
            height=15,
            exportselection=False,
        )
        self.lista_generos.pack(in_=contenedor_generos, side="left", fill="x", expand=True)
        desplazamiento_generos = tk.Scrollbar(
            contenedor_generos,
            command=self.lista_generos.yview,
            bg=PANEL,
            troughcolor=PANEL,
            activebackground=LINEA,
            relief="flat",
            bd=0,
            width=8,
        )
        desplazamiento_generos.pack(side="right", fill="y")
        self.lista_generos.configure(yscrollcommand=desplazamiento_generos.set)
        self.lista_generos.bind("<<ListboxSelect>>", self._seleccionar_genero)

        self._etiqueta_sidebar("TU CONEXIÓN")
        self.indicador = tk.Label(
            self.sidebar,
            text="●  Conectando...",
            bg=PANEL,
            fg=SUAVE,
            font=("Segoe UI", 9),
            anchor="w",
        )
        self.indicador.pack(fill="x", padx=25, pady=(3, 10))

        tk.Button(
            self.sidebar,
            text="↻   Actualizar biblioteca",
            command=self.actualizar_catalogo,
            bg=PANEL_CLARO,
            fg=TEXTO,
            activebackground=VERDE_OSCURO,
            activeforeground=VERDE,
            relief="flat",
            bd=0,
            padx=12,
            pady=10,
            anchor="w",
            font=("Segoe UI", 9, "bold"),
            cursor="hand2",
        ).pack(fill="x", padx=18, pady=(8, 14))

        tk.Label(
            self.sidebar,
            text="HECHO PARA ESCUCHAR",
            bg=PANEL,
            fg="#55645b",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="bottom", pady=18)

    def _etiqueta_sidebar(self, texto: str) -> None:
        tk.Label(
            self.sidebar,
            text=texto,
            bg=PANEL,
            fg="#64736a",
            font=("Segoe UI", 8, "bold"),
            anchor="w",
        ).pack(fill="x", padx=25, pady=(0, 9))

    def _crear_contenido(self, parent: tk.Frame) -> None:
        header = tk.Frame(parent, bg=FONDO)
        header.grid(row=0, column=0, sticky="ew", padx=34, pady=(26, 16))
        header.columnconfigure(1, weight=1)
        tk.Label(
            header,
            text="BIBLIOTECA PERSONAL",
            bg=FONDO,
            fg=SUAVE,
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w")
        busqueda = tk.Frame(header, bg=PANEL, highlightbackground=LINEA, highlightthickness=1)
        busqueda.grid(row=0, column=1, sticky="e")
        tk.Label(
            busqueda,
            text="⌕",
            bg=PANEL,
            fg=SUAVE,
            font=("Segoe UI", 16),
        ).pack(side="left", padx=(10, 5))
        self.campo_busqueda = tk.Entry(
            busqueda,
            textvariable=self.filtro,
            bg=PANEL,
            fg=TEXTO,
            insertbackground=VERDE,
            relief="flat",
            font=("Segoe UI", 10),
            width=28,
        )
        self.campo_busqueda.pack(side="left", padx=(0, 12), ipady=10)
        self.campo_busqueda.bind("<Return>", lambda _event: None)

        self.hero = tk.Frame(parent, bg="#18251d", height=174)
        self.hero.grid(row=1, column=0, sticky="ew", padx=34, pady=(0, 22))
        self.hero.grid_propagate(False)
        self.hero.columnconfigure(0, weight=1)
        self.hero.rowconfigure(0, weight=1)
        textos = tk.Frame(self.hero, bg="#18251d")
        textos.grid(row=0, column=0, sticky="nsew", padx=24, pady=22)
        tk.Label(
            textos,
            text="AHORA EN TU BIBLIOTECA",
            bg="#18251d",
            fg=VERDE,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")
        tk.Label(
            textos,
            textvariable=self.genero_texto,
            bg="#18251d",
            fg=TEXTO,
            font=("Segoe UI", 23, "bold"),
        ).pack(anchor="w", pady=(6, 2))
        self.resumen = tk.Label(
            textos,
            text="Organiza tus canciones por estilo y encuentra tu próximo sonido.",
            bg="#18251d",
            fg="#aab6ad",
            font=("Segoe UI", 10),
        )
        self.resumen.pack(anchor="w")
        arte = tk.Canvas(
            self.hero,
            width=180,
            height=174,
            bg="#18251d",
            highlightthickness=0,
        )
        arte.grid(row=0, column=1, sticky="e")
        self._dibujar_arte(arte)

        encabezado_lista = tk.Frame(parent, bg=FONDO)
        encabezado_lista.grid(row=2, column=0, sticky="ew", padx=34, pady=(0, 10))
        encabezado_lista.columnconfigure(0, weight=1)
        tk.Label(
            encabezado_lista,
            text="Tus canciones",
            bg=FONDO,
            fg=TEXTO,
            font=("Segoe UI", 16, "bold"),
        ).grid(row=0, column=0, sticky="w")
        self.conteo = tk.Label(
            encabezado_lista,
            text="0 pistas",
            bg=FONDO,
            fg=SUAVE,
            font=("Segoe UI", 9),
        )
        self.conteo.grid(row=0, column=1, sticky="e")

        lista = tk.Frame(parent, bg=PANEL, highlightbackground=LINEA, highlightthickness=1)
        lista.grid(row=3, column=0, sticky="nsew", padx=34, pady=(0, 24))
        lista.rowconfigure(0, weight=1)
        lista.columnconfigure(0, weight=1)
        columnas = ("numero", "titulo", "artista", "album", "genero", "duracion")
        self.tabla = ttk.Treeview(
            lista,
            columns=columnas,
            show="headings",
            selectmode="browse",
            style="Library.Treeview",
        )
        encabezados = {
            "numero": ("#", 42),
            "titulo": ("TÍTULO", 260),
            "artista": ("ARTISTA", 175),
            "album": ("ÁLBUM", 150),
            "genero": ("GÉNERO", 130),
            "duracion": ("DURACIÓN", 72),
        }
        for columna, (nombre, ancho) in encabezados.items():
            self.tabla.heading(columna, text=nombre)
            self.tabla.column(
                columna,
                width=ancho,
                minwidth=44,
                anchor="center" if columna in ("numero", "duracion") else "w",
                stretch=columna not in ("numero", "duracion"),
            )
        self.tabla.tag_configure("odd", background=PANEL)
        self.tabla.tag_configure("even", background="#151e1a")
        self.tabla.grid(row=0, column=0, sticky="nsew", padx=(8, 0), pady=8)
        scrollbar = ttk.Scrollbar(
            lista,
            orient=tk.VERTICAL,
            command=self.tabla.yview,
            style="Library.Vertical.TScrollbar",
        )
        scrollbar.grid(row=0, column=1, sticky="ns", padx=(0, 6), pady=8)
        self.tabla.configure(yscrollcommand=scrollbar.set)

    def _dibujar_arte(self, canvas: tk.Canvas) -> None:
        canvas.create_oval(40, 25, 164, 149, fill="#22352a", outline="")
        canvas.create_oval(53, 38, 151, 136, fill="#101713", outline="#526d55", width=2)
        canvas.create_oval(62, 47, 142, 127, outline="#314b37", width=2)
        canvas.create_oval(72, 57, 132, 117, outline="#314b37", width=2)
        canvas.create_oval(83, 68, 121, 106, fill=VERDE, outline="")
        canvas.create_oval(96, 81, 108, 93, fill="#19241c", outline="")
        canvas.create_line(24, 133, 76, 81, fill=VERDE, width=3, capstyle=tk.ROUND)

    def _crear_reproductor(self, parent: tk.Frame) -> None:
        barra = tk.Frame(parent, bg="#111815", height=112, highlightbackground=LINEA, highlightthickness=1)
        barra.grid(row=1, column=0, columnspan=2, sticky="ew")
        barra.grid_propagate(False)
        barra.columnconfigure(0, weight=1)
        barra.columnconfigure(1, weight=2)
        barra.columnconfigure(2, weight=1)

        actual = tk.Frame(barra, bg="#111815")
        actual.grid(row=0, column=0, sticky="ew", padx=24, pady=18)
        tk.Label(
            actual,
            text="♫",
            bg=VERDE_OSCURO,
            fg=VERDE,
            width=3,
            height=2,
            font=("Segoe UI Symbol", 15),
        ).pack(side="left", padx=(0, 12))
        meta = tk.Frame(actual, bg="#111815")
        meta.pack(side="left", fill="x", expand=True)
        tk.Label(
            meta,
            textvariable=self.titulo_actual,
            bg="#111815",
            fg=TEXTO,
            font=("Segoe UI", 10, "bold"),
            anchor="w",
        ).pack(fill="x")
        tk.Label(
            meta,
            textvariable=self.artista_actual,
            bg="#111815",
            fg=SUAVE,
            font=("Segoe UI", 9),
            anchor="w",
        ).pack(fill="x", pady=(3, 0))

        centro = tk.Frame(barra, bg="#111815")
        centro.grid(row=0, column=1, sticky="nsew", pady=(10, 8))
        controles = tk.Frame(centro, bg="#111815")
        controles.pack()
        self._boton_icono(controles, "⏮", self.anterior).pack(side="left", padx=10)
        self.boton_play = tk.Button(
            controles,
            text="▶",
            command=self.reproducir_seleccion,
            bg=VERDE,
            fg="#10170f",
            activebackground="#cff89a",
            activeforeground="#10170f",
            relief="flat",
            bd=0,
            width=4,
            height=1,
            font=("Segoe UI Symbol", 14, "bold"),
            cursor="hand2",
        )
        self.boton_play.pack(side="left", padx=4)
        self._boton_icono(controles, "⏭", self.siguiente).pack(side="left", padx=10)
        self._boton_icono(controles, "■", self.detener).pack(side="left", padx=8)

        progreso = tk.Frame(centro, bg="#111815")
        progreso.pack(fill="x", padx=14, pady=(5, 0))
        tk.Label(
            progreso,
            textvariable=self.tiempo_actual,
            bg="#111815",
            fg=SUAVE,
            font=("Segoe UI", 8),
        ).pack(side="left")
        self.barra_progreso = ttk.Scale(
            progreso,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            command=self._mover_progreso,
            style="Library.Horizontal.TScale",
        )
        self.barra_progreso.pack(side="left", fill="x", expand=True, padx=10)
        self.barra_progreso.bind("<ButtonPress-1>", self._iniciar_busqueda)
        self.barra_progreso.bind("<ButtonRelease-1>", self._terminar_busqueda)
        tk.Label(
            progreso,
            textvariable=self.tiempo_total,
            bg="#111815",
            fg=SUAVE,
            font=("Segoe UI", 8),
        ).pack(side="left")

        volumen = tk.Frame(barra, bg="#111815")
        volumen.grid(row=0, column=2, sticky="e", padx=24)
        tk.Label(volumen, text="VOL", bg="#111815", fg=SUAVE, font=("Segoe UI", 8, "bold")).pack(side="left")
        self.control_volumen = ttk.Scale(
            volumen,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.volumen,
            command=self._cambiar_volumen,
            style="Library.Horizontal.TScale",
            length=115,
        )
        self.control_volumen.pack(side="left", padx=(10, 0))

    def _boton_icono(self, parent: tk.Widget, texto: str, comando: object) -> tk.Button:
        return tk.Button(
            parent,
            text=texto,
            command=comando,
            bg="#111815",
            fg="#b6c2b8",
            activebackground="#1b2820",
            activeforeground=VERDE,
            relief="flat",
            bd=0,
            width=3,
            font=("Segoe UI Symbol", 12),
            cursor="hand2",
        )

    def actualizar_catalogo(self) -> None:
        self.estado.set("Sincronizando catálogo...")
        self.indicador.configure(text="●  Conectando...", fg=SUAVE)

        def tarea() -> None:
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                    catalogo = solicitar_catalogo(sock)
                self.cola.put(("catalogo", catalogo))
            except OSError as exc:
                self.cola.put(("error_catalogo", str(exc)))

        threading.Thread(target=tarea, daemon=True).start()

    def _seleccionar_genero(self, _event: tk.Event) -> None:
        seleccion = self.lista_generos.curselection()
        if not seleccion:
            return
        indice = seleccion[0]
        if indice == 0:
            self.genero_actual = "Toda la música"
        elif indice == 1:
            self.genero_actual = "Sin género"
        else:
            self.genero_actual = self.generos[indice - 2]
        self.genero_texto.set(self.genero_actual)
        self._dibujar_canciones()

    def _actualizar_generos(self) -> None:
        conteos: dict[str, int] = {}
        for cancion in self.catalogo:
            genero = str(cancion.get("genero") or "Sin género").strip() or "Sin género"
            conteos[genero] = conteos.get(genero, 0) + 1
        self.generos = sorted(
            (genero for genero in conteos if genero != "Sin género"),
            key=lambda genero: (-conteos[genero], genero.casefold()),
        )
        valores = ["♫   Toda la música", "◌   Sin género"]
        valores.extend(f"♪   {genero}  ·  {conteos[genero]}" for genero in self.generos)
        self.lista_generos.delete(0, tk.END)
        for valor in valores:
            self.lista_generos.insert(tk.END, valor)
        indice_actual = 0
        if self.genero_actual == "Sin género":
            indice_actual = 1
        elif self.genero_actual in self.generos:
            indice_actual = self.generos.index(self.genero_actual) + 2
        else:
            self.genero_actual = "Toda la música"
        self.lista_generos.selection_set(indice_actual)
        self.lista_generos.activate(indice_actual)
        self.genero_texto.set(self.genero_actual)

    def _dibujar_canciones(self, *_args: object) -> None:
        self.tabla.delete(*self.tabla.get_children())
        visibles = self._canciones_visibles()
        self.conteo.configure(text=f"{len(visibles)} pistas")
        for orden, (indice, cancion) in enumerate(visibles, start=1):
            self.tabla.insert(
                "",
                tk.END,
                iid=str(indice),
                values=(
                    f"{orden:02d}",
                    cancion.get("titulo", "Sin título"),
                    cancion.get("artista", "Desconocido"),
                    cancion.get("album", "Desconocido"),
                    cancion.get("genero", "Sin género"),
                    self._formatear_tiempo(cancion.get("duracion_seg", 0)),
                ),
                tags=("even" if orden % 2 == 0 else "odd",),
            )
        if self.genero_actual == "Toda la música":
            self.resumen.configure(text="Explora tus estilos, encuentra un sonido y dale play.")
        else:
            self.resumen.configure(
                text=f"{len(visibles)} canciones para escuchar en la categoría seleccionada."
            )

    def _canciones_visibles(self) -> list[tuple[int, dict]]:
        termino = self.filtro.get().strip().casefold()
        resultado = []
        for indice, cancion in enumerate(self.catalogo):
            genero = str(cancion.get("genero") or "Sin género").strip() or "Sin género"
            if self.genero_actual == "Sin género" and genero != "Sin género":
                continue
            if self.genero_actual not in ("Toda la música", "Sin género") and genero != self.genero_actual:
                continue
            texto = " ".join(
                str(cancion.get(campo, ""))
                for campo in ("titulo", "artista", "album", "genero", "archivo")
            ).casefold()
            if termino and termino not in texto:
                continue
            resultado.append((indice, cancion))
        return resultado

    def reproducir_seleccion(self) -> None:
        seleccion = self.tabla.selection()
        if not seleccion:
            visibles = self._canciones_visibles()
            if not visibles:
                self.estado.set("No hay canciones en esta vista.")
                return
            self._reproducir_cancion(visibles[0][0])
            return
        self._reproducir_cancion(int(seleccion[0]))

    def _reproducir_cancion(self, indice: int) -> None:
        cancion = self.catalogo[indice]
        nombre = cancion.get("archivo")
        if not isinstance(nombre, str) or not nombre:
            messagebox.showerror("Catálogo inválido", "La canción no tiene un nombre de archivo válido.")
            return
        self.estado.set(f"Preparando «{cancion.get('titulo', nombre)}»...")
        self.boton_play.configure(state=tk.DISABLED)

        def tarea() -> None:
            try:
                ruta = os.path.join(CARPETA_DESCARGAS, nombre)
                if not os.path.isfile(ruta):
                    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
                        ruta = descargar_cancion_gbn(sock, nombre)
                self.cola.put(("reproducir", (ruta, cancion)))
            except OSError as exc:
                self.cola.put(("error_descarga", str(exc)))

        threading.Thread(target=tarea, daemon=True).start()

    def _reproducir_lista(self, indice: int) -> None:
        nombre = self.catalogo[indice].get("archivo")
        ruta = os.path.join(CARPETA_DESCARGAS, nombre) if isinstance(nombre, str) else ""
        if not ruta or not os.path.isfile(ruta):
            self._reproducir_cancion(indice)
            return
        self._iniciar_pista(ruta, self.catalogo[indice])

    def _iniciar_pista(self, ruta: str, cancion: dict) -> None:
        try:
            self.reproductor.reproducir(ruta)
        except RuntimeError as exc:
            self.estado.set("No se pudo iniciar el audio.")
            self.boton_play.configure(state=tk.NORMAL)
            messagebox.showerror("Error de reproducción", str(exc))
            return
        self.cancion_actual = cancion
        self.duracion_actual = max(0, int(cancion.get("duracion_seg") or 0))
        self.titulo_actual.set(cancion.get("titulo", cancion.get("archivo", "Sin título")))
        self.artista_actual.set(cancion.get("artista", "Artista desconocido"))
        self.tiempo_total.set(self._formatear_tiempo(self.duracion_actual))
        self.barra_progreso.configure(to=max(1, self.duracion_actual))
        self.barra_progreso.set(0)
        self.boton_play.configure(text="❚❚", state=tk.NORMAL)
        self.boton_play.configure(command=self.alternar_pausa)
        self.estado.set("Reproduciendo ahora")
        for item in self.tabla.selection():
            self.tabla.selection_remove(item)
        for iid in self.tabla.get_children():
            if self.catalogo[int(iid)] is cancion:
                self.tabla.selection_set(iid)
                self.tabla.see(iid)
                break

    def alternar_pausa(self) -> None:
        try:
            pausado = self.reproductor.alternar_pausa()
            self.boton_play.configure(text="▶" if pausado else "❚❚")
            self.estado.set("En pausa" if pausado else "Reproduciendo ahora")
        except RuntimeError as exc:
            messagebox.showerror("Error de audio", str(exc))

    def anterior(self) -> None:
        self._saltar_pista(-1)

    def siguiente(self) -> None:
        self._saltar_pista(1)

    def _saltar_pista(self, cambio: int) -> None:
        visibles = self._canciones_visibles()
        if not visibles:
            return
        indices = [indice for indice, _ in visibles]
        actual = next(
            (pos for pos, (_, cancion) in enumerate(visibles) if cancion is self.cancion_actual),
            -1 if cambio > 0 else 1,
        )
        nuevo = (actual + cambio) % len(indices)
        self._reproducir_lista(indices[nuevo])

    def detener(self) -> None:
        try:
            self.reproductor.detener()
        except RuntimeError as exc:
            messagebox.showerror("Error de audio", str(exc))
        self.barra_progreso.set(0)
        self.tiempo_actual.set("0:00")
        self.boton_play.configure(text="▶", state=tk.NORMAL)
        self.boton_play.configure(command=self.reproducir_seleccion)
        self.estado.set("Reproducción detenida")

    def _iniciar_busqueda(self, _event: tk.Event) -> None:
        self.seleccionando_posicion = True

    def _terminar_busqueda(self, _event: tk.Event) -> None:
        self.seleccionando_posicion = False
        if self.duracion_actual and self.reproductor.abierto:
            try:
                self.reproductor.buscar(float(self.barra_progreso.get()))
            except RuntimeError as exc:
                self.estado.set(str(exc))

    def _mover_progreso(self, valor: str) -> None:
        if self.seleccionando_posicion and self.duracion_actual:
            self.tiempo_actual.set(self._formatear_tiempo(int(float(valor))))

    def _cambiar_volumen(self, valor: str) -> None:
        try:
            self.reproductor.volumen(float(valor) / 100)
        except RuntimeError as exc:
            self.estado.set(str(exc))

    def _atajo_pausa(self, _event: tk.Event) -> str | None:
        if self.reproductor.abierto:
            self.alternar_pausa()
            return "break"
        return None

    def _doble_click(self, event: tk.Event) -> None:
        if event.widget is self.tabla:
            self.reproducir_seleccion()

    def _actualizar_reproduccion(self) -> None:
        if self.reproductor.abierto and not self.reproductor.pausado:
            if not self.reproductor.reproduciendo():
                self.reproductor.detener()
                self._saltar_pista(1)
            else:
                posicion = self.reproductor.posicion()
                if not self.seleccionando_posicion:
                    self.barra_progreso.set(posicion)
                    self.tiempo_actual.set(self._formatear_tiempo(posicion))
        self.root.after(250, self._actualizar_reproduccion)

    def _procesar_cola(self) -> None:
        while True:
            try:
                tipo, valor = self.cola.get_nowait()
            except queue.Empty:
                break
            if tipo == "catalogo":
                self.catalogo = valor
                self._actualizar_generos()
                self._dibujar_canciones()
                self.indicador.configure(text="●  Biblioteca conectada", fg=VERDE)
                self.estado.set(f"{len(self.catalogo)} canciones listas para sonar")
            elif tipo == "error_catalogo":
                self.indicador.configure(text="●  Servidor desconectado", fg="#ff7c7c")
                self.estado.set("No se pudo conectar con el servidor.")
                messagebox.showerror("Sin conexión", valor)
            elif tipo == "reproducir":
                ruta, cancion = valor
                self.boton_play.configure(state=tk.NORMAL)
                if ruta is None:
                    self.estado.set("No se pudo descargar la canción.")
                else:
                    self._iniciar_pista(ruta, cancion)
            elif tipo == "error_descarga":
                self.boton_play.configure(state=tk.NORMAL)
                self.estado.set("Error al descargar la canción.")
                messagebox.showerror("Error de descarga", valor)
        self.root.after(100, self._procesar_cola)

    @staticmethod
    def _formatear_tiempo(segundos: object) -> str:
        try:
            total = max(0, int(segundos))
        except (TypeError, ValueError):
            total = 0
        return f"{total // 60}:{total % 60:02d}"

    def cerrar(self) -> None:
        try:
            self.reproductor.cerrar()
        except RuntimeError as exc:
            messagebox.showerror("Error de audio", str(exc))
        self.root.destroy()


def iniciar_interfaz() -> None:
    root = tk.Tk()
    InterfazReproductor(root)
    root.mainloop()
