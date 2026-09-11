import { useState, useEffect, useCallback, useRef } from 'react'
import { Card, CardContent } from '../../components/ui'
import { Button } from '../../components/ui/Button'
import { Select } from '../../components/ui/Select'
import { Badge } from '../../components/ui/Badge'
import { EmptyState } from '../../components/ui/EmptyState'
import { cn } from '../../lib/utils'
import { knowledgeBaseApi } from '../../lib/api'
import {
  Search,
  Send,
  RefreshCw,
  Database,
  Loader2,
  AlertCircle,
  CheckCircle,
  FileText,
  Building2,
  BookOpen,
  Zap,
  MessageSquare,
  Copy,
} from 'lucide-react'

interface KnowledgeSourceCitation {
  id: number
  source_type: string
  source_id: number
  content: string
  metadata: Record<string, any>
  similarity: number
}

interface KnowledgeBaseStats {
  total_embeddings: number
  by_source_type: Record<string, number>
  by_project: Record<string, number>
  organization_id: number
}

interface Message {
  role: 'user' | 'assistant'
  content: string
  sources?: KnowledgeSourceCitation[]
  confidence?: number
  timestamp: Date
}

const SOURCE_TYPE_ICONS: Record<string, React.ReactNode> = {
  DELAY_REASON: <AlertCircle className="w-4 h-4 text-amber-400" />,
  PRODUCTIVITY_BENCHMARK: <Zap className="w-4 h-4 text-green-400" />,
  GLOSSARY_MAPPING: <BookOpen className="w-4 h-4 text-blue-400" />,
  WBS_NODE: <FileText className="w-4 h-4 text-purple-400" />,
  PROJECT_SUMMARY: <Building2 className="w-4 h-4 text-cyan-400" />,
  CLOSED_PROJECT_SUMMARY: <Building2 className="w-4 h-4 text-gray-400" />,
}

const SOURCE_TYPE_LABELS: Record<string, string> = {
  DELAY_REASON: 'Delay Reason',
  PRODUCTIVITY_BENCHMARK: 'Productivity Benchmark',
  GLOSSARY_MAPPING: 'Glossary Mapping',
  WBS_NODE: 'WBS Activity',
  PROJECT_SUMMARY: 'Project Summary',
  CLOSED_PROJECT_SUMMARY: 'Closed Project Summary',
}

export function KnowledgeBase() {
  const [projectId] = useState<number | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [isIndexing, setIsIndexing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [messages, setMessages] = useState<Message[]>([])
  const [inputValue, setInputValue] = useState('')
  const [stats, setStats] = useState<KnowledgeBaseStats | null>(null)
  const [sourceTypes, setSourceTypes] = useState<string[]>([])
  const [selectedSourceTypes, setSelectedSourceTypes] = useState<string[]>([])
  const [topK, setTopK] = useState(10)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const fetchStats = useCallback(async () => {
    if (!projectId) return
    try {
      const res = await knowledgeBaseApi.getStats(projectId)
      setStats(res.data)
    } catch (err: any) {
      console.error('Failed to fetch stats:', err)
    }
  }, [projectId])

  const fetchSourceTypes = useCallback(async () => {
    try {
      const res = await knowledgeBaseApi.getSourceTypes()
      setSourceTypes(res.data)
    } catch (err: any) {
      console.error('Failed to fetch source types:', err)
    }
  }, [])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  useEffect(() => {
    scrollToBottom()
  }, [messages])

  useEffect(() => {
    fetchStats()
    fetchSourceTypes()
  }, [fetchStats, fetchSourceTypes])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!inputValue.trim() || isLoading) return

    const userMessage = inputValue.trim()
    setInputValue('')
    setError(null)

    const newUserMessage: Message = {
      role: 'user',
      content: userMessage,
      timestamp: new Date(),
    }
    setMessages(prev => [...prev, newUserMessage])
    setIsLoading(true)

    try {
      const res = await knowledgeBaseApi.query({
        query: userMessage,
        project_id: projectId || undefined,
        source_types: selectedSourceTypes.length > 0 ? selectedSourceTypes : undefined,
        top_k: topK,
      })

      const assistantMessage: Message = {
        role: 'assistant',
        content: res.data.answer,
        sources: res.data.sources,
        confidence: res.data.confidence,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, assistantMessage])
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to query knowledge base')
      const errorMessage: Message = {
        role: 'assistant',
        content: `Error: ${err.response?.data?.detail || 'Failed to query knowledge base'}`,
        timestamp: new Date(),
      }
      setMessages(prev => [...prev, errorMessage])
    } finally {
      setIsLoading(false)
    }
  }

  const handleIndex = async () => {
    if (isIndexing) return
    setIsIndexing(true)
    setError(null)

    try {
      const res = await knowledgeBaseApi.index(projectId || undefined)
      setStats(null)
      fetchStats()
      alert(res.data.message)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to index knowledge base')
    } finally {
      setIsIndexing(false)
    }
  }

  const copyToClipboard = (text: string) => {
    navigator.clipboard.writeText(text)
  }

  if (!projectId) {
    return (
      <div className="space-y-6 animate-fade-in">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
          <div>
            <h1 className="text-3xl font-bold text-white">Knowledge Base</h1>
            <p className="text-textMuted mt-1">Query institutional memory with natural language</p>
          </div>
        </div>
        <Card>
          <CardContent className="p-8">
            <EmptyState
              icon={<Building2 className="w-16 h-16" />}
              title="No project selected"
              description="Select a project from the schedule or dashboard to query the knowledge base."
            />
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-white">Knowledge Base</h1>
          <p className="text-textMuted mt-1">Query institutional memory with natural language — delay causes, productivity benchmarks, glossary terms, WBS activities, and project summaries</p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="secondary" onClick={handleIndex} disabled={isIndexing}>
            <Database className="w-4 h-4" />
            {isIndexing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Indexing...
              </>
            ) : (
              'Build Index'
            )}
          </Button>
          <Button variant="secondary" onClick={fetchStats}>
            <RefreshCw className="w-4 h-4" />
            Refresh Stats
          </Button>
        </div>
      </div>

      {/* Stats Bar */}
      {stats && (
        <Card className="border-border/50">
          <CardContent className="p-4">
            <div className="flex flex-wrap items-center gap-6">
              <div className="flex items-center gap-2">
                <Database className="w-5 h-5 text-green-400" />
                <span className="text-sm text-textMuted">Total Embeddings:</span>
                <span className="text-lg font-bold text-white">{stats.total_embeddings}</span>
              </div>
{Object.entries(stats.by_source_type).map(([type, count]) => {
                const icon = SOURCE_TYPE_ICONS[type] || <FileText className="w-3 h-3" />;
                return (
                  <Badge key={type} variant="neutral" className="gap-1">
                    {icon}
                    {SOURCE_TYPE_LABELS[type]}: {count}
                  </Badge>
                );
              })}
            </div>
          </CardContent>
        </Card>
      )}

      {/* Filters */}
      <Card className="border-border/50">
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <label className="text-sm text-textMuted">Sources:</label>
              <Select
                value={selectedSourceTypes.join(',')}
                onChange={(e) => setSelectedSourceTypes(e.target.value ? e.target.value.split(',') : [])}
                className="w-64"
                options={sourceTypes.map(st => ({ value: st, label: SOURCE_TYPE_LABELS[st] }))}
                multiple
              />
            </div>
            <div className="flex items-center gap-2">
              <label className="text-sm text-textMuted">Top K:</label>
              <Select
                value={String(topK)}
                onChange={(e) => setTopK(parseInt(e.target.value))}
                className="w-32"
                options={[
                  { value: "5", label: "5" },
                  { value: "10", label: "10" },
                  { value: "20", label: "20" },
                  { value: "50", label: "50" },
                ]}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Chat Area */}
      <Card className="flex-1 flex flex-col min-h-[500px]">
        <div className="flex-1 overflow-y-auto p-4 space-y-6" role="log" aria-live="polite">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full min-h-[300px] text-textMuted">
              <MessageSquare className="w-16 h-16 mb-4 opacity-50" />
              <p className="text-lg">Ask a question about your project's institutional memory</p>
              <p className="text-sm mt-2">Examples:</p>
              <div className="mt-4 space-y-2 text-left max-w-md">
                <div className="p-3 bg-surfaceRaised rounded-lg border border-border/50 text-sm">
                  "What are the top delay causes for piping installation?"
                </div>
                <div className="p-3 bg-surfaceRaised rounded-lg border border-border/50 text-sm">
                  "Show me productivity benchmarks for electrical discipline"
                </div>
                <div className="p-3 bg-surfaceRaised rounded-lg border border-border/50 text-sm">
                  "What does 'WBS' stand for in our glossary?"
                </div>
                <div className="p-3 bg-surfaceRaised rounded-lg border border-border/50 text-sm">
                  "Show me all activities for the highway project"
                </div>
              </div>
            </div>
          )}

          {messages.map((message, index) => (
            <div key={index} className={cn('flex gap-3 animate-fade-in', message.role === 'user' && 'flex-row-reverse')}>
              <div className={cn('w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0', message.role === 'user' ? 'bg-white/10' : 'bg-green-400/20')}>
                {message.role === 'user' ? (
                  <Search className="w-4 h-4 text-white" />
                ) : (
                  <Zap className="w-4 h-4 text-green-400" />
                )}
              </div>
              <div className={cn('flex-1 max-w-3xl', message.role === 'user' ? 'text-right' : '')}>
                <div className={cn('inline-block p-4 rounded-2xl', message.role === 'user' ? 'bg-white/10' : 'bg-surfaceRaised border border-border/50')}>
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>

{message.role === 'assistant' && message.sources && message.sources.length > 0 && (
                    <div className="mt-3 space-y-2">
                      <p className="text-xs text-textMuted flex items-center gap-2">
                        <CheckCircle className="w-3 h-3" />
                        Sources ({message.sources.length}) • Confidence: {((message.confidence ?? 0) * 100).toFixed(0)}%
                    </p>
                    <div className="space-y-2">
                      {message.sources.map((source, srcIndex) => (
                        <div key={srcIndex} className="p-3 bg-surface border border-border/50 rounded-lg">
                          <div className="flex items-start gap-2">
                            <span className="text-xs font-medium text-textMuted flex-shrink-0">[{source.id}]</span>
                            <div className="flex-1 min-w-0">
                              <div className="flex items-center gap-2 mb-1">
                                {SOURCE_TYPE_ICONS[source.source_type] || <FileText className="w-3 h-3 text-textMuted" />}
                                <span className="text-sm font-medium text-white">{SOURCE_TYPE_LABELS[source.source_type]}</span>
                                <Badge variant="neutral" className="text-xs">
                                  {source.metadata?.discipline || source.metadata?.project_name || source.metadata?.activity_code || 'N/A'}
                                </Badge>
                                <Badge variant="neutral" className="text-xs text-green-400">
                                  {(source.similarity * 100).toFixed(0)}% match
                                </Badge>
                              </div>
                              <p className="text-sm text-textMuted line-clamp-2">{source.content}</p>
                              <div className="flex items-center gap-2 mt-2">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => copyToClipboard(source.content)}
                                  className="text-xs h-6 px-2"
                                >
                                  <Copy className="w-3 h-3" />
                                  Copy
                                </Button>
                              </div>
                            </div>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                <p className="text-xs text-textMuted mt-1">{message.timestamp.toLocaleTimeString()}</p>
              </div>
            </div>
          ))}

          {isLoading && (
            <div className="flex gap-3 animate-fade-in">
              <div className="w-8 h-8 rounded-full bg-green-400/20 flex items-center justify-center flex-shrink-0">
                <Loader2 className="w-4 h-4 text-green-400 animate-spin" />
              </div>
              <div className="bg-surfaceRaised border border-border/50 rounded-2xl p-4 animate-pulse">
                <div className="h-4 bg-border/50 rounded w-3/4" />
                <div className="h-4 bg-border/50 rounded w-1/2 mt-2" />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* Input Area */}
        <div className="border-t border-border p-4">
          <form onSubmit={handleSubmit} className="flex gap-3">
            <textarea
              ref={inputRef}
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              placeholder="Ask about delays, productivity, glossary terms, activities, or projects..."
              className="flex-1 bg-surface border border-border/50 rounded-lg p-3 text-white placeholder-textMuted resize-none min-h-[50px] max-h-[150px] focus:outline-none focus:border-white/30 focus:ring-1 focus:ring-white/20"
              rows={1}
              disabled={isLoading}
              style={{ minHeight: '50px' }}
            />
            <Button
              type="submit"
              disabled={!inputValue.trim() || isLoading}
              className="h-10 flex-shrink-0"
              aria-label="Send query"
            >
              <Send className="w-4 h-4" />
            </Button>
          </form>
          <p className="text-xs text-textMuted mt-2 text-center">
            Press Enter to send, Shift+Enter for new line
          </p>
        </div>
      </Card>

      {error && (
        <Card className="border-status-new-activity/50">
          <CardContent className="p-4 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-status-new-activity" />
            <span className="text-status-new-activity">{error}</span>
            <Button variant="ghost" size="sm" onClick={() => setError(null)}>
              Dismiss
            </Button>
          </CardContent>
        </Card>
      )}
    </div>
  )
}