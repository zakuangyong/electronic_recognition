import { describe, expect, expectTypeOf, it, vi } from 'vitest'

import { fetchConfig } from '../config'
import type {
  AppConfig,
  LayoutRouterMode,
  RecognitionMode,
  SearchMode,
} from '../../types/config'

describe('fetchConfig', () => {
  it('reads runtime config from api endpoint', async () => {
    const payload: AppConfig = {
      model: 'gpt-4.1',
      api_key_configured: true,
      knowledge_path: 'data/index/components.json',
      component_count: 12,
      custom_rules_path: 'data/index/custom_rules.json',
      custom_rule_count: 2,
      reference_batch_size: 4,
      recognition_mode: 'hybrid',
      layout_routing_enabled: true,
      layout_router_mode: 'hybrid',
      search_enabled: true,
      search_mode: 'hybrid',
      search_auto_index: false,
      open_recognition_concurrency: 2,
      correction_batch_size: 8,
      correction_candidate_limit: 5,
    }
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(JSON.stringify(payload)),
    })

    const result = await fetchConfig(fetchImpl)

    expect(fetchImpl).toHaveBeenCalledWith('/api/config')
    expect(result).toEqual(payload)
  })

  it('throws normalized backend error for failed requests', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      text: vi.fn().mockResolvedValue(
        JSON.stringify({ detail: { message: '配置读取失败' } }),
      ),
    })

    await expect(fetchConfig(fetchImpl)).rejects.toThrow('配置读取失败')
  })

  it('falls back gracefully for failed non-json responses', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: false,
      text: vi.fn().mockResolvedValue('<html>server error</html>'),
    })

    await expect(fetchConfig(fetchImpl)).rejects.toThrow('配置读取失败')
  })

  it('falls back gracefully for empty successful responses', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(''),
    })

    await expect(fetchConfig(fetchImpl)).rejects.toThrow('配置读取失败')
  })

  it('rejects successful responses with empty config object', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue('{}'),
    })

    await expect(fetchConfig(fetchImpl)).rejects.toThrow('配置读取失败')
  })

  it('rejects successful responses with invalid config modes', async () => {
    const fetchImpl = vi.fn().mockResolvedValue({
      ok: true,
      text: vi.fn().mockResolvedValue(
        JSON.stringify({
          model: 'gpt-4.1',
          api_key_configured: true,
          knowledge_path: 'data/index/components.json',
          component_count: 12,
          custom_rules_path: 'data/index/custom_rules.json',
          custom_rule_count: 2,
          reference_batch_size: 4,
          recognition_mode: 'standard',
          layout_routing_enabled: true,
          layout_router_mode: 'hybrid',
          search_enabled: true,
          search_mode: 'semantic',
          search_auto_index: false,
          open_recognition_concurrency: 2,
          correction_batch_size: 8,
          correction_candidate_limit: 5,
        }),
      ),
    })

    await expect(fetchConfig(fetchImpl)).rejects.toThrow('配置读取失败')
  })

  it('uses narrowed config mode types', () => {
    const payload: AppConfig = {
      model: 'gpt-4.1',
      api_key_configured: true,
      knowledge_path: 'data/index/components.json',
      component_count: 12,
      custom_rules_path: 'data/index/custom_rules.json',
      custom_rule_count: 2,
      reference_batch_size: 4,
      recognition_mode: 'hybrid',
      layout_routing_enabled: true,
      layout_router_mode: 'rules',
      search_enabled: true,
      search_mode: 'bm25',
      search_auto_index: false,
      open_recognition_concurrency: 2,
      correction_batch_size: 8,
      correction_candidate_limit: 5,
    }

    expectTypeOf(payload.recognition_mode).toEqualTypeOf<RecognitionMode>()
    expectTypeOf(payload.layout_router_mode).toEqualTypeOf<LayoutRouterMode>()
    expectTypeOf(payload.search_mode).toEqualTypeOf<SearchMode>()
  })
})
