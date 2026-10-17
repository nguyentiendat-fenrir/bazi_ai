// Problem Details (RFC 9457) from the API, as one error type the screens can render.

export interface FieldError {
  path: string
  message: string
}

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly title: string
  readonly detail: string | null
  readonly fieldErrors: FieldError[]
  readonly requestId: string | null
  readonly etag: string | null
  readonly retryAfter: number | null

  constructor(status: number, code: string, title: string, options: {
    detail?: string | null, fieldErrors?: FieldError[], requestId?: string | null,
    etag?: string | null, retryAfter?: number | null,
  } = {}) {
    super(options.detail || title)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.title = title
    this.detail = options.detail ?? null
    this.fieldErrors = options.fieldErrors ?? []
    this.requestId = options.requestId ?? null
    this.etag = options.etag ?? null
    this.retryAfter = options.retryAfter ?? null
  }

  /** The message for one form field, e.g. fieldError('body.reason'). */
  fieldError(path: string): string | undefined {
    return this.fieldErrors.find((f) => f.path === path)?.message
  }
}

function text(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null
}

/** Build an ApiError from a response status, its parsed body (any shape) and headers. */
export function toApiError(status: number, body: unknown, headers?: Headers | null): ApiError {
  const problem = (body && typeof body === 'object' ? body : {}) as Record<string, unknown>
  const fields = Array.isArray(problem.field_errors) ? problem.field_errors : []
  const retry = Number(headers?.get('Retry-After'))
  return new ApiError(
    status,
    text(problem.code) ?? (status >= 500 ? 'SERVER_ERROR' : 'HTTP_' + status),
    text(problem.title) ?? 'Request failed',
    {
      detail: text(problem.detail),
      fieldErrors: fields
        .filter((f): f is Record<string, unknown> => !!f && typeof f === 'object')
        .map((f) => ({ path: String(f.path ?? ''), message: String(f.message ?? '') })),
      requestId: text(problem.request_id) ?? headers?.get('X-Request-ID') ?? null,
      etag: headers?.get('ETag') ?? null,
      retryAfter: Number.isFinite(retry) && retry > 0 ? retry : null,
    },
  )
}

export function networkError(cause: unknown): ApiError {
  const error = new ApiError(0, 'NETWORK_ERROR', 'API unreachable', {
    detail: cause instanceof Error ? cause.message : null,
  })
  return error
}

// Vietnamese messages for the codes a user can act on; anything else shows the API title.
const MESSAGES: Record<string, string> = {
  NETWORK_ERROR: 'Không kết nối được máy chủ API. Kiểm tra dịch vụ rồi thử lại.',
  AUTH_REQUIRED: 'Phiên đăng nhập đã hết hoặc thông tin đăng nhập không đúng.',
  CSRF_FAILED: 'Phiên làm việc thiếu mã bảo vệ. Hãy đăng nhập lại.',
  ORIGIN_REJECTED: 'Yêu cầu bị từ chối vì không đến từ địa chỉ được phép.',
  FORBIDDEN: 'Tài khoản của bạn không có quyền thực hiện thao tác này.',
  RATE_LIMITED: 'Đăng nhập sai quá nhiều lần. Hãy đợi rồi thử lại.',
  NOT_FOUND: 'Không tìm thấy dữ liệu, hoặc bạn không có quyền xem.',
  VALIDATION_ERROR: 'Dữ liệu chưa hợp lệ. Kiểm tra các trường được đánh dấu.',
  REVISION_MISMATCH: 'Dữ liệu đã được người khác thay đổi. Tải bản mới trước khi lưu.',
  PRECONDITION_REQUIRED: 'Thiếu phiên bản dữ liệu khi lưu. Tải lại trang rồi thử lại.',
  IDEMPOTENCY_IN_PROGRESS: 'Yêu cầu giống hệt đang được xử lý. Đợi giây lát.',
  JOB_ACTIVE: 'Phiên bản này đang có job chạy. Đợi job xong hoặc hủy job.',
  VERSION_WITHDRAWN: 'Phiên bản sách đã bị thu hồi.',
  SERVER_ERROR: 'Máy chủ gặp lỗi. Thử lại sau; nếu lặp lại, gửi mã yêu cầu cho quản trị.',
}

export function describe(error: unknown): string {
  if (error instanceof ApiError) {
    return MESSAGES[error.code] ?? error.detail ?? error.title
  }
  return error instanceof Error ? error.message : String(error)
}
