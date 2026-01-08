#!/usr/bin/env python3
import argparse, time, struct, sys
import serial

MAGIC = b"\x55\xAA"
VER   = 1

TYPE_HELLO       = 0x02
TYPE_HELLO_ACK   = 0x03
TYPE_DATA        = 0x01
TYPE_SETBAUD     = 0x10
TYPE_SETBAUD_ACK = 0x11
TYPE_STATS_REQ   = 0x20
TYPE_STATS_RSP   = 0x21

# CRC16-CCITT (0x1021), init 0xFFFF
def crc16_ccitt(data: bytes, poly=0x1021, init=0xFFFF) -> int:
    crc = init
    for b in data:
        crc ^= (b << 8)
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ poly) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF

def pack_frame(ftype: int, seq: int, payload: bytes) -> bytes:
    # On-wire header: MAGIC(2) VER(1) TYPE(1) SEQ(4) LEN(2) + PAYLOAD + CRC(2)
    header = struct.pack("<2sBBIH", MAGIC, VER, ftype, seq, len(payload))
    body = struct.pack("<BBIH", VER, ftype, seq, len(payload)) + payload
    c = crc16_ccitt(body)
    return header + payload + struct.pack("<H", c)

class FrameParser:
    def __init__(self):
        self.buf = bytearray()

    def feed(self, data: bytes):
        self.buf.extend(data)

    def pop_one(self):
        # find MAGIC, parse a full frame if present
        while True:
            if len(self.buf) < 2:
                return None

            idx = self.buf.find(MAGIC)
            if idx < 0:
                self.buf.clear()
                return None

            if idx > 0:
                del self.buf[:idx]

            # Need full fixed header
            if len(self.buf) < (2 + 1 + 1 + 4 + 2):
                return None

            _, ver, ftype, seq, ln = struct.unpack_from("<2sBBIH", self.buf, 0)

            # Bad version => shift and resync
            if ver != VER:
                del self.buf[:2]
                continue

            total_len = 2 + 1 + 1 + 4 + 2 + ln + 2
            if len(self.buf) < total_len:
                return None

            payload_off = 2 + 1 + 1 + 4 + 2
            payload = bytes(self.buf[payload_off : payload_off + ln])
            recv_crc = struct.unpack_from("<H", self.buf, payload_off + ln)[0]

            body = struct.pack("<BBIH", ver, ftype, seq, ln) + payload
            calc_crc = crc16_ccitt(body)

            del self.buf[:total_len]
            return (ftype, seq, payload, recv_crc == calc_crc)

class Stats:
    def __init__(self):
        self.expected_seq = None

        self.total_ok = 0
        self.total_bad = 0
        self.total_missed = 0
        self.total_dup = 0

        self.win_ok = 0
        self.win_bad = 0
        self.win_missed = 0
        self.win_dup = 0
        self.win_bytes = 0

        self.last_print = time.time()

    def on_good_data(self, seq: int, payload_len: int):
        if self.expected_seq is None:
            self.expected_seq = (seq + 1) & 0xFFFFFFFF
        else:
            exp = self.expected_seq
            if seq > exp:
                miss = seq - exp
                self.total_missed += miss
                self.win_missed += miss
                self.expected_seq = (seq + 1) & 0xFFFFFFFF
            elif seq == exp:
                self.expected_seq = (exp + 1) & 0xFFFFFFFF
            else:
                self.total_dup += 1
                self.win_dup += 1

        self.total_ok += 1
        self.win_ok += 1
        self.win_bytes += payload_len

    def on_bad(self):
        self.total_bad += 1
        self.win_bad += 1

    @staticmethod
    def loss_pct(ok, missed, bad):
        denom = ok + missed + bad
        return 0.0 if denom <= 0 else (missed + bad) * 100.0 / denom

    def maybe_print(self, tag="RX"):
        now = time.time()
        if now - self.last_print >= 1.0:
            lp = self.loss_pct(self.win_ok, self.win_missed, self.win_bad)
            tp = self.loss_pct(self.total_ok, self.total_missed, self.total_bad)
            sys.stdout.write(
                f"[{time.strftime('%F %T')}] {tag} "
                f"win_ok={self.win_ok} win_miss={self.win_missed} win_bad={self.win_bad} win_dup={self.win_dup} "
                f"loss_win={lp:.3f}% | "
                f"total_ok={self.total_ok} total_miss={self.total_missed} total_bad={self.total_bad} total_dup={self.total_dup} "
                f"loss_total={tp:.3f}%\n"
            )
            sys.stdout.flush()
            self.last_print = now

    def snapshot_and_reset_window(self):
        lp = self.loss_pct(self.win_ok, self.win_missed, self.win_bad)
        tp = self.loss_pct(self.total_ok, self.total_missed, self.total_bad)
        snap = {
            "win_ok": self.win_ok,
            "win_miss": self.win_missed,
            "win_bad": self.win_bad,
            "win_dup": self.win_dup,
            "win_bytes": self.win_bytes,
            "loss_win": lp,
            "total_ok": self.total_ok,
            "total_miss": self.total_missed,
            "total_bad": self.total_bad,
            "total_dup": self.total_dup,
            "loss_total": tp,
        }
        self.win_ok = 0
        self.win_miss = 0
        self.win_bad = 0
        self.win_dup = 0
        self.win_bytes = 0
        return snap

def set_serial(ser: serial.Serial, baud: int):
    ser.baudrate = baud
    ser.reset_input_buffer()
    ser.reset_output_buffer()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default="/dev/ttyTHS0")
    ap.add_argument("--baud-list", default="115200,230400,460800,921600,1500000,2000000,3000000,4000000")
    ap.add_argument("--scan-dwell-ms", type=int, default=200, help="scan dwell per baud")
    ap.add_argument("--idle-timeout", type=float, default=3.0, help="seconds no frames => back to scanning")
    args = ap.parse_args()

    baud_list = [int(x) for x in args.baud_list.split(",") if x.strip()]
    ser = serial.Serial(args.port, baudrate=baud_list[0], timeout=0.05)

    parser = FrameParser()
    st = Stats()

    locked = False
    last_rx_time = time.time()

    def send(ftype, seq, payload=b""):
        try:
            ser.write(pack_frame(ftype, seq, payload))
        except Exception as e:
            sys.stdout.write(f"[{time.strftime('%F %T')}] SEND error: {e}\n")
            sys.stdout.flush()

    while True:
        if not locked:
            # scan to find HELLO
            for b in baud_list:
                set_serial(ser, b)
                t_end = time.time() + args.scan_dwell_ms / 1000.0

                while time.time() < t_end:
                    data = ser.read(4096)
                    if data:
                        parser.feed(data)
                        while True:
                            fr = parser.pop_one()
                            if fr is None:
                                break

                            ftype, seq, payload, ok = fr
                            if ftype == TYPE_HELLO and ok:
                                locked = True
                                last_rx_time = time.time()
                                # ack include current baud (u32)
                                send(TYPE_HELLO_ACK, 0, struct.pack("<I", b))
                                sys.stdout.write(f"[{time.strftime('%F %T')}] LOCKED at baud={b}\n")
                                sys.stdout.flush()
                                break

                    if locked:
                        break

                if locked:
                    break

            continue

        # locked mode: receive frames
        data = ser.read(4096)
        if data:
            parser.feed(data)

        while True:
            fr = parser.pop_one()
            if fr is None:
                break

            ftype, seq, payload, ok = fr
            last_rx_time = time.time()

            if not ok:
                st.on_bad()
                continue

            if ftype == TYPE_DATA:
                st.on_good_data(seq, len(payload))

            elif ftype == TYPE_HELLO:
                # ===== FIX (关键修复) =====
                # master 在切波特率后会发 HELLO 做确认；locked 模式必须回复 HELLO_ACK
                cur = int(ser.baudrate)
                send(TYPE_HELLO_ACK, 0, struct.pack("<I", cur))

            elif ftype == TYPE_SETBAUD:
                # payload: u32 newbaud
                if len(payload) >= 4:
                    newb = struct.unpack("<I", payload[:4])[0]
                    # send ack first at old baud, then switch (更稳)
                    send(TYPE_SETBAUD_ACK, 0, struct.pack("<I", newb))
                    ser.flush()
                    time.sleep(0.02)
                    set_serial(ser, newb)
                    sys.stdout.write(f"[{time.strftime('%F %T')}] SWITCH baud -> {newb}\n")
                    sys.stdout.flush()

            elif ftype == TYPE_STATS_REQ:
                snap = st.snapshot_and_reset_window()
                rsp = struct.pack(
                    "<IIIIIfIIIIIf",
                    snap["win_ok"], snap["win_miss"], snap["win_bad"], snap["win_dup"], snap["win_bytes"],
                    float(snap["loss_win"]),
                    snap["total_ok"], snap["total_miss"], snap["total_bad"], snap["total_dup"], 0,
                    float(snap["loss_total"]),
                )
                send(TYPE_STATS_RSP, 0, rsp)

        st.maybe_print("RX")

        # idle timeout => back to scanning
        if time.time() - last_rx_time > args.idle_timeout:
            locked = False
            st = Stats()
            parser = FrameParser()
            sys.stdout.write(f"[{time.strftime('%F %T')}] IDLE timeout, back to scanning...\n")
            sys.stdout.flush()

if __name__ == "__main__":
    main()

