import math
import time
from pathlib import Path

import ffmpeg
from celery.utils.serialization import UnpickleableExceptionWrapper
from loguru import logger

from ..celery import app

DEFAULT_FRAGMENT_PATH = "fragments"
DEFAULT_M3U8_NAME = "index.m3u8"
DEFAULT_VIDEO_NAME = "video.mp4"


def video_check(video_path: str) -> Path:
    """Проверить видео файл."""
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Видео файл {video_path} не найден.")

    if not Path(video_path).is_file():
        raise IsADirectoryError(f"{video_path} не является файлом.")

    return Path(video_path)


def directory_check(directory_path: str) -> Path:
    """Проверить папку с фрагментами."""
    if not Path(directory_path).exists():
        raise FileNotFoundError(f"Папка с фрагментами {directory_path} не найдена.")

    if not Path(directory_path).is_dir():
        raise NotADirectoryError(f"{directory_path} не является папкой.")

    return Path(directory_path)


def wait_check(func, /, *args, **kwargs):
    while True:
        try:
            return func(*args, **kwargs)

        except Exception:  # noqa: BLE001
            time.sleep(0.1)


def video_check_ffprobe(video_path: str) -> Path:
    p = Path(video_path)
    if not p.exists():
        raise FileNotFoundError(video_path)

    try:
        probe = ffmpeg.probe(str(p))
    except ffmpeg.Error as e:
        raise ValueError(f"ffprobe не смог прочитать файл: {e.stderr.decode()}") from e

    # Ищем видеопоток
    video_streams = [
        stream
        for stream in probe.get("streams", [])
        if stream.get("codec_type") == "video"
    ]
    if not video_streams:
        raise ValueError("Видеодорожка отсутствует")

    # Дополнительно: проверить, что длительность > 0, кодек читаемый и т.д.
    duration = float(probe.get("format", {}).get("duration", 0))
    if duration <= 0:
        raise ValueError("Длительность видео нулевая или не определена")

    return p


@app.task
def process_video(
    video_path: str,
    fragment_path: str = DEFAULT_FRAGMENT_PATH,
    m3u8_name: str = DEFAULT_M3U8_NAME,
    wait: bool = True,
) -> None:
    """Создать видео фрагменты в формате `.ts`.

    Args:
        video_path (str): Путь к видео файлу.
        fragment_path (str, optional): Путь к папке с фрагментами. Если не указан, будет создан в папке с видео.
        m3u8_name (str, optional): Имя файла `.m3u8`. Будет создан в папке с фрагментами. Если не указан, будет создан с именем `index.m3u8`.
    """
    if wait:
        path = wait_check(video_check, video_path)

    else:
        path = video_check(video_path)

    if fragment_path == DEFAULT_FRAGMENT_PATH:
        fragment_path = path.parent / Path(fragment_path)

    else:
        fragment_path = Path(fragment_path)

    if not fragment_path.exists():
        fragment_path.mkdir(parents=True, exist_ok=True)

    if not Path(fragment_path).is_dir():
        raise NotADirectoryError(f"{fragment_path} не является папкой.")

    video = ffmpeg.input(str(path))
    ffmpeg.output(
        video,
        str(fragment_path / m3u8_name),
        format="hls",
        hls_time=10,
        hls_list_size=0,
        hls_segment_filename=str(fragment_path / "segment_%03d.ts"),
        **{"c:v": "libx264", "preset": "fast"},  # или "medium", "veryfast" и т.д.
    ).run()


@app.task
def create_thumbanil(
    video_path: str,
    thumbanil_path: str = "poster.jpg",
    timestamp: str = "00:00:05",
    wait: bool = True,
) -> None:
    """Создать постер для видео.

    Args:
        video_path (str): Путь к видео файлу.
        thumbanil (str, optional): Путь к постеру. Если не указан, будет создан в папке с видео с названием `poster.jpg`. По умолчанию poster.jpg.
        timestamp (str, optional): Время для создания постера. По умолчанию 00:00:05.
    """
    if wait:
        path = wait_check(video_check, video_path)
        wait_check(video_check_ffprobe, video_path)

    else:
        path = video_check(video_path)

    for attempt in range(1, 4):
        try:
            (
                ffmpeg.input(video_path, ss=timestamp)  # ss - seek to timestamp
                .output(
                    str(path.parent / thumbanil_path), vframes=1
                )  # vframes=1 - один кадр
                .run(overwrite_output=True)
            )
            return
        except UnpickleableExceptionWrapper:
            logger.warning("Проблема с видео", extra={"video_path": video_path})
            time.sleep(2 * attempt)


@app.task
def process_fragments(
    fragment_path: str, video_path: str | None = None, wait: bool = True
) -> None:
    """Соеденить все фрагменты в один `.mp4` файл.
    Требует наличии в папке фрагментов с расширением `.ts`.

    Args:
        fragment_path (str): Путь к папке с фрагментами.
        video_name (str, optional): Путь к видео, если не указан будет создан в директории с фрагментами. По умолчанию None.
    """
    if wait:
        path = wait_check(directory_check, fragment_path)

    else:
        path = directory_check(fragment_path)
    files = sorted(f for f in path.glob("*.ts") if f.is_file())

    if not files:
        raise FileNotFoundError("Фрагменты по шаблону '*.ts' не найдены.")

    output_path = (
        str(path.parent / DEFAULT_VIDEO_NAME) if video_path is None else video_path
    )

    file_path = path / "files.txt"

    with open(file_path, "w") as file:
        file.writelines(f"file '{f.absolute().as_posix()}'\n" for f in files)

    try:
        (
            ffmpeg.input(str(file_path), format="concat", safe=0)
            .output(output_path, c="copy", loglevel="warning")
            .run()
        )

    except ffmpeg.Error as e:
        print("Ошибка при создание видео:", e.stderr)

    finally:
        if file_path.exists():
            file_path.unlink()


@app.task
def create_m3u8(
    fragment_path: str,
    m3u8_name: str = DEFAULT_M3U8_NAME,
    fragment_pattern: str = "segment_*.ts",
    wait: bool = True,
) -> None:
    """
    Создаёт m3u8-плейлист из .ts фрагментов.
    """
    if wait:
        path = wait_check(directory_check, fragment_path)

    else:
        path = directory_check(fragment_path)

    files = sorted(f for f in path.glob(fragment_pattern) if f.is_file())

    if not files:
        raise FileNotFoundError(
            f"Фрагменты по шаблону '{fragment_pattern}' не найдены."
        )

    result = ["#EXTM3U", "#EXT-X-VERSION:3", "#EXT-X-MEDIA-SEQUENCE:0"]

    max_duration = 0.0

    def get_duration(file: Path) -> float:
        try:
            probe = ffmpeg.probe(str(file))
            dur = probe.get("format", {}).get("duration")
            return float(dur) if dur else 10.0

        except ffmpeg.Error as e:
            print(f"Ошибка при анализе длительности {file.name}: {e}")
            return 10.0

    for file in files:
        duration = get_duration(file)
        max_duration = max(max_duration, duration)
        result.append(f"#EXTINF:{duration:.3f},\n{file.name}")

    result.insert(2, f"#EXT-X-TARGETDURATION:{math.ceil(max_duration)}")
    result.append("#EXT-X-ENDLIST")

    (path / m3u8_name).write_text("\n".join(result), encoding="utf-8")
